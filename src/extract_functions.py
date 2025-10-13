#!/usr/bin/env python3
"""
Extract full function context from filtered commits.
Following KNighter methodology: extract complete function code that was modified.
"""

import json
import subprocess
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class FunctionExtractor:
    """Extract full function context from git commits."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
    
    def get_file_at_commit(self, commit_sha: str, file_path: str) -> Optional[str]:
        """Get file content at specific commit."""
        try:
            result = subprocess.run(
                ['git', 'show', f'{commit_sha}:{file_path}'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except Exception as e:
            logger.warning(f"Failed to get file {file_path} at {commit_sha[:8]}: {e}")
            return None
    
    def extract_function_from_diff(self, diff_text: str) -> List[str]:
        """Extract function names from diff hunks."""
        functions = []
        # Match @@ -line,count +line,count @@ function_name
        pattern = r'@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@\s+(.+?)$'
        
        for line in diff_text.split('\n'):
            match = re.search(pattern, line)
            if match:
                func_context = match.group(1).strip()
                # Extract function name (remove parameters, etc.)
                # Common patterns: "int func_name(...)" or "func_name(...)"
                func_match = re.search(r'(\w+)\s*\(', func_context)
                if func_match:
                    functions.append(func_match.group(1))
        
        return list(set(functions))  # Remove duplicates
    
    def find_function_bounds(self, content: str, function_name: str) -> Optional[Tuple[int, int]]:
        """
        Find start and end line numbers of a function in C code.
        Returns (start_line, end_line) or None if not found.
        """
        lines = content.split('\n')
        
        # Find function definition
        # Pattern: return_type function_name(...) or function_name(...)
        func_pattern = re.compile(
            rf'^\s*(?:\w+\s+)*{re.escape(function_name)}\s*\(',
            re.MULTILINE
        )
        
        start_line = None
        for i, line in enumerate(lines):
            if func_pattern.search(line):
                start_line = i
                break
        
        if start_line is None:
            return None
        
        # Find matching closing brace
        brace_count = 0
        in_function = False
        
        for i in range(start_line, len(lines)):
            line = lines[i]
            
            # Count braces
            for char in line:
                if char == '{':
                    brace_count += 1
                    in_function = True
                elif char == '}':
                    brace_count -= 1
                    
                    # Found matching closing brace
                    if in_function and brace_count == 0:
                        return (start_line, i)
        
        return None
    
    def extract_function_code(self, content: str, function_name: str) -> Optional[str]:
        """Extract complete function code."""
        bounds = self.find_function_bounds(content, function_name)
        if bounds is None:
            return None
        
        start_line, end_line = bounds
        lines = content.split('\n')
        return '\n'.join(lines[start_line:end_line + 1])
    
    def process_commit(self, commit: Dict) -> Dict:
        """
        Process a single commit and extract function context.
        Returns enriched commit data with function context.
        """
        sha = commit['sha']
        diff = commit.get('diff', '')
        
        # Extract function names from diff
        functions = self.extract_function_from_diff(diff)
        
        if not functions:
            logger.debug(f"No functions found in diff for {sha[:8]}")
            return commit
        
        # Get parent commit (buggy version)
        parent_sha = f"{sha}^"
        
        # Extract function context for each modified file
        function_contexts = {}
        
        # Parse diff to get modified files
        file_pattern = re.compile(r'^diff --git a/(.+?) b/(.+?)$', re.MULTILINE)
        files = file_pattern.findall(diff)
        
        for old_file, new_file in files:
            # Use new_file path (after rename if any)
            file_path = new_file
            
            # Get buggy version (before patch)
            buggy_content = self.get_file_at_commit(parent_sha, file_path)
            
            # Get patched version (after patch)
            patched_content = self.get_file_at_commit(sha, file_path)
            
            if buggy_content and patched_content:
                for func_name in functions:
                    # Extract function from both versions
                    buggy_func = self.extract_function_code(buggy_content, func_name)
                    patched_func = self.extract_function_code(patched_content, func_name)
                    
                    if buggy_func or patched_func:
                        key = f"{file_path}::{func_name}"
                        function_contexts[key] = {
                            'file': file_path,
                            'function': func_name,
                            'buggy_code': buggy_func,
                            'patched_code': patched_func
                        }
        
        # Add function contexts to commit
        commit['function_contexts'] = function_contexts
        commit['extracted_functions'] = len(function_contexts)
        
        return commit


def main():
    """Main execution."""
    logger.info("=" * 60)
    logger.info("SQuire: Extract Function Context from Commits")
    logger.info("=" * 60)
    
    # Paths
    base_dir = Path(__file__).parent.parent
    input_file = base_dir / 'mined_patches_curated' / 'filtered_off_by_one.json'
    output_file = base_dir / 'mined_patches_curated' / 'commits_with_functions.json'
    repo_path = base_dir / 'linux'
    
    # Load filtered commits
    logger.info(f"Loading commits from: {input_file}")
    with open(input_file, 'r') as f:
        commits = json.load(f)
    logger.info(f"Loaded {len(commits)} commits")
    
    # Initialize extractor
    extractor = FunctionExtractor(str(repo_path))
    
    # Process commits
    logger.info("Extracting function contexts...")
    enriched_commits = []
    total_functions = 0
    
    for i, commit in enumerate(commits, 1):
        if i % 10 == 0:
            logger.info(f"Processing commit {i}/{len(commits)}...")
        
        enriched = extractor.process_commit(commit)
        enriched_commits.append(enriched)
        total_functions += enriched.get('extracted_functions', 0)
    
    # Save results
    logger.info(f"Saving {len(enriched_commits)} commits to: {output_file}")
    with open(output_file, 'w') as f:
        json.dump(enriched_commits, f, indent=2)
    
    # Statistics
    commits_with_funcs = sum(1 for c in enriched_commits if c.get('extracted_functions', 0) > 0)
    
    logger.info("=" * 60)
    logger.info(f"Total commits processed: {len(enriched_commits)}")
    logger.info(f"Commits with functions: {commits_with_funcs}")
    logger.info(f"Total functions extracted: {total_functions}")
    logger.info(f"Average functions per commit: {total_functions / len(enriched_commits):.2f}")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
