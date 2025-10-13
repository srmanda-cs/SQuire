#!/usr/bin/env python3
"""
LLM-based pattern analysis for off-by-one errors.
Following KNighter methodology: analyze bug patterns from patches.
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class PatternAnalyzer:
    """Analyze bug patterns using LLM via OpenAI-compatible API."""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.model = model
        
    def create_analysis_prompt(self, commit: Dict) -> str:
        """
        Create prompt for LLM to analyze bug pattern.
        Following KNighter's pattern analysis stage.
        """
        # Extract relevant information
        subject = commit.get('subject', 'Unknown')
        message = commit.get('message', '')
        diff = commit.get('diff', '')
        
        # Get function contexts if available
        function_contexts = commit.get('function_contexts', {})
        
        prompt = f"""You are a static analysis expert analyzing Linux kernel bug fixes to identify off-by-one error patterns.

# Task
Analyze this bug-fix patch and determine:
1. Is this truly an off-by-one error? (YES/NO)
2. What is the specific bug pattern?
3. What are the key indicators that make this an off-by-one error?
4. How can this pattern be detected statically?

# Commit Information
Subject: {subject}

Commit Message:
{message}

# Diff Patch
{diff}
"""

        # Add function context if available
        if function_contexts:
            prompt += "\n# Function Context\n"
            for key, ctx in function_contexts.items():
                prompt += f"\n## {key}\n"
                if ctx.get('buggy_code'):
                    prompt += f"\n### Buggy Version (Before Patch):\n```c\n{ctx['buggy_code']}\n```\n"
                if ctx.get('patched_code'):
                    prompt += f"\n### Patched Version (After Patch):\n```c\n{ctx['patched_code']}\n```\n"
        
        prompt += """
# Response Format
Provide your analysis in the following JSON format:

{
  "is_off_by_one": true/false,
  "confidence": "high/medium/low",
  "bug_pattern": "Detailed description of the bug pattern",
  "key_indicators": [
    "Indicator 1",
    "Indicator 2",
    ...
  ],
  "detection_strategy": "How to detect this pattern statically",
  "coccinelle_feasible": true/false,
  "reasoning": "Explanation of your analysis"
}

Focus on patterns that can be detected through static analysis (e.g., array bounds, loop conditions, buffer sizes).
"""
        return prompt
    
    def analyze_commit(self, commit: Dict) -> Optional[Dict]:
        """Analyze a single commit for off-by-one patterns."""
        try:
            prompt = self.create_analysis_prompt(commit)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert in static analysis and Linux kernel security. Analyze bug patterns precisely and provide structured JSON responses."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent analysis
                max_tokens=2048,
            )
            
            # Extract JSON from response
            text = response.choices[0].message.content.strip()
            
            # Try to extract JSON (handle markdown code blocks)
            if '```json' in text:
                json_start = text.find('```json') + 7
                json_end = text.find('```', json_start)
                text = text[json_start:json_end].strip()
            elif '```' in text:
                json_start = text.find('```') + 3
                json_end = text.find('```', json_start)
                text = text[json_start:json_end].strip()
            
            analysis = json.loads(text)
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to analyze commit: {e}")
            return None
    
    def batch_analyze(self, commits: List[Dict], max_commits: Optional[int] = None) -> List[Dict]:
        """Analyze multiple commits."""
        if max_commits:
            commits = commits[:max_commits]
        
        results = []
        for i, commit in enumerate(commits, 1):
            logger.info(f"Analyzing commit {i}/{len(commits)}: {commit['sha'][:8]}")
            
            analysis = self.analyze_commit(commit)
            
            if analysis:
                result = {
                    'sha': commit['sha'],
                    'subject': commit.get('subject', ''),
                    'analysis': analysis,
                    'has_functions': commit.get('extracted_functions', 0) > 0
                }
                results.append(result)
                
                # Log result
                is_obo = analysis.get('is_off_by_one', False)
                confidence = analysis.get('confidence', 'unknown')
                logger.info(f"  → Off-by-one: {is_obo}, Confidence: {confidence}")
            else:
                logger.warning(f"  → Analysis failed")
        
        return results


def main():
    """Main execution."""
    logger.info("=" * 60)
    logger.info("SQuire: LLM-Based Pattern Analysis")
    logger.info("=" * 60)
    
    # Get configuration from environment
    api_key = os.getenv('API_KEY')
    base_url = os.getenv('BASE_URL')
    model = os.getenv('LLM_MODEL')
    
    if not all([api_key, base_url, model]):
        logger.error("Missing required environment variables:")
        logger.error("  API_KEY, BASE_URL, LLM_MODEL")
        logger.error("Please configure your .env file")
        return
    
    logger.info(f"Using model: {model}")
    logger.info(f"Base URL: {base_url}")
    
    # Paths
    base_dir = Path(__file__).parent.parent
    input_file = base_dir / 'mined_patches_curated' / 'commits_with_functions.json'
    output_file = base_dir / 'mined_patches_curated' / 'pattern_analysis.json'
    
    # Load commits
    logger.info(f"Loading commits from: {input_file}")
    with open(input_file, 'r') as f:
        commits = json.load(f)
    logger.info(f"Loaded {len(commits)} commits")
    
    # Filter to commits with function context for better analysis
    commits_with_funcs = [c for c in commits if c.get('extracted_functions', 0) > 0]
    logger.info(f"Commits with function context: {len(commits_with_funcs)}")
    
    # Initialize analyzer
    analyzer = PatternAnalyzer(api_key, base_url, model)
    
    # Analyze commits (start with a small batch for testing)
    logger.info("Starting pattern analysis...")
    logger.info("Analyzing first 50 commits as initial batch...")
    
    results = analyzer.batch_analyze(commits_with_funcs, max_commits=50)
    
    # Save results
    logger.info(f"Saving {len(results)} analyses to: {output_file}")
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Statistics
    confirmed_obo = sum(1 for r in results if r['analysis'].get('is_off_by_one', False))
    high_confidence = sum(1 for r in results 
                         if r['analysis'].get('is_off_by_one', False) 
                         and r['analysis'].get('confidence') == 'high')
    coccinelle_feasible = sum(1 for r in results 
                             if r['analysis'].get('is_off_by_one', False)
                             and r['analysis'].get('coccinelle_feasible', False))
    
    logger.info("=" * 60)
    logger.info(f"Total analyzed: {len(results)}")
    logger.info(f"Confirmed off-by-one: {confirmed_obo} ({confirmed_obo/len(results)*100:.1f}%)")
    logger.info(f"High confidence: {high_confidence}")
    logger.info(f"Coccinelle feasible: {coccinelle_feasible}")
    logger.info("=" * 60)
    
    # Show sample results
    logger.info("\nSample confirmed off-by-one patterns:")
    for r in results[:5]:
        if r['analysis'].get('is_off_by_one', False):
            logger.info(f"\n{r['sha'][:8]}: {r['subject'][:60]}")
            logger.info(f"  Pattern: {r['analysis'].get('bug_pattern', 'N/A')[:80]}")
            logger.info(f"  Confidence: {r['analysis'].get('confidence', 'N/A')}")


if __name__ == '__main__':
    main()
