#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
filter_commits.py
-----------------
Filter commits from the raw mined data to identify potential off-by-one errors.
Applies multiple configurable filters to reduce ~14K commits to a manageable set.
"""

import os
import re
import json
import logging
from typing import List, Dict, Any
from datetime import datetime

# ------------------------------------------------------------
# Configuration - Adjust these as needed
# ------------------------------------------------------------

RAW_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "mined_patches_raw"))
FILTERED_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "mined_patches_curated"))

INPUT_FILE = "all_v5.16_to_v5.17.json"
OUTPUT_FILE = "filtered_off_by_one.json"
STATS_FILE = "filter_stats.txt"
SAMPLE_FILE = "sample_commits.txt"

# Filter thresholds (configurable)
CONFIG = {
    # Filter 1: Line changes
    "max_lines_changed": 3,  # Option C: 1-3 lines
    
    # Filter 2: Keywords in commit message (case-insensitive)
    "keywords": [
        "off-by-one", "off by one", "obo",
        "boundary", "bounds", "bound",
        "index", "overflow", "underflow",
        "array out of bounds", "buffer overflow",
        "out-of-bounds", "out of bounds",
    ],
    
    # Filter 3: Boundary operators in diff
    "boundary_patterns": [
        r"[<>]=?",  # <, <=, >, >=
        r"[\+\-]\s*1\b",  # +1, -1
        r"\bsize\s*-\s*1\b",  # size - 1
        r"\blen\s*-\s*1\b",  # len - 1
        r"\blength\s*-\s*1\b",  # length - 1
    ],
    
    # Filter 4: Loop/array context keywords
    "context_keywords": [
        "for", "while",  # loops
        "[", "]",  # array access
        "memcpy", "memset", "kmalloc", "kzalloc",  # memory ops
        "strlen", "strncpy", "snprintf", "strlcpy",  # string ops
    ],
    
    # Filter 5: File types (extensions to include)
    "file_extensions": [".c", ".h"],
    
    # Filter 6: Noise exclusion keywords
    "exclude_keywords": [
        "typo", "comment", "whitespace", "formatting",
        "indentation", "style", "cleanup",
    ],
    
    # Filter 7: Size constraints
    "max_total_loc": 20,  # Total lines changed
    "max_files_changed": 2,  # Number of files
    "max_patch_size_kb": 5,  # Patch size in KB
    
    # Sample size for manual review
    "sample_size": 5,
}

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("filter_commits")

# ------------------------------------------------------------
# Filter Functions
# ------------------------------------------------------------


def filter_line_changes(commit: Dict[str, Any]) -> bool:
    """Filter 1: Keep commits with 1-3 lines changed."""
    total_changes = commit["loc_added"] + commit["loc_removed"]
    return 1 <= total_changes <= CONFIG["max_lines_changed"]


def filter_keywords(commit: Dict[str, Any]) -> bool:
    """Filter 2: Check for off-by-one keywords in commit message."""
    text = (commit["subject"] + " " + commit["body"]).lower()
    return any(kw.lower() in text for kw in CONFIG["keywords"])


def filter_boundary_operators(commit: Dict[str, Any]) -> bool:
    """Filter 3: Check for boundary operator changes in diff."""
    diff = commit["diff"]
    for pattern in CONFIG["boundary_patterns"]:
        if re.search(pattern, diff):
            return True
    return False


def filter_context(commit: Dict[str, Any]) -> bool:
    """Filter 4: Check for loop/array context in diff."""
    diff = commit["diff"]
    return any(kw in diff for kw in CONFIG["context_keywords"])


def filter_file_types(commit: Dict[str, Any]) -> bool:
    """Filter 5: Keep only .c and .h files."""
    files = commit.get("files_changed", [])
    if not files:
        return False
    return any(
        any(f.endswith(ext) for ext in CONFIG["file_extensions"])
        for f in files
    )


def filter_exclude_noise(commit: Dict[str, Any]) -> bool:
    """Filter 6: Exclude commits with noise keywords."""
    text = (commit["subject"] + " " + commit["body"]).lower()
    return not any(kw.lower() in text for kw in CONFIG["exclude_keywords"])


def filter_size_constraints(commit: Dict[str, Any]) -> bool:
    """Filter 7: Apply size constraints."""
    if commit["total_loc"] > CONFIG["max_total_loc"]:
        return False
    if commit["num_files_changed"] > CONFIG["max_files_changed"]:
        return False
    patch_size_kb = commit["patch_size_bytes"] / 1024
    if patch_size_kb > CONFIG["max_patch_size_kb"]:
        return False
    return True


# ------------------------------------------------------------
# Main Filtering Pipeline
# ------------------------------------------------------------


def apply_filters(commits: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Apply all filters in sequence and track statistics."""
    
    stats = {
        "total": len(commits),
        "after_line_changes": 0,
        "after_keywords": 0,
        "after_boundary_ops": 0,
        "after_context": 0,
        "after_file_types": 0,
        "after_exclude_noise": 0,
        "after_size_constraints": 0,
        "final": 0,
    }
    
    log.info(f"Starting with {stats['total']} commits")
    
    # Filter 1: Line changes
    commits = [c for c in commits if filter_line_changes(c)]
    stats["after_line_changes"] = len(commits)
    log.info(f"After line changes filter: {len(commits)} commits")
    
    # Filter 2: Keywords
    commits = [c for c in commits if filter_keywords(c)]
    stats["after_keywords"] = len(commits)
    log.info(f"After keywords filter: {len(commits)} commits")
    
    # Filter 3: Boundary operators
    commits = [c for c in commits if filter_boundary_operators(c)]
    stats["after_boundary_ops"] = len(commits)
    log.info(f"After boundary operators filter: {len(commits)} commits")
    
    # Filter 4: Context
    commits = [c for c in commits if filter_context(c)]
    stats["after_context"] = len(commits)
    log.info(f"After context filter: {len(commits)} commits")
    
    # Filter 5: File types
    commits = [c for c in commits if filter_file_types(c)]
    stats["after_file_types"] = len(commits)
    log.info(f"After file types filter: {len(commits)} commits")
    
    # Filter 6: Exclude noise
    commits = [c for c in commits if filter_exclude_noise(c)]
    stats["after_exclude_noise"] = len(commits)
    log.info(f"After exclude noise filter: {len(commits)} commits")
    
    # Filter 7: Size constraints
    commits = [c for c in commits if filter_size_constraints(c)]
    stats["after_size_constraints"] = len(commits)
    log.info(f"After size constraints filter: {len(commits)} commits")
    
    stats["final"] = len(commits)
    
    return commits, stats


def save_stats(stats: Dict[str, int], output_path: str):
    """Save filtering statistics to a text file."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("COMMIT FILTERING STATISTICS\n")
        f.write("=" * 60 + "\n\n")
        
        f.write(f"Total commits:                    {stats['total']:>6}\n")
        f.write(f"After line changes (1-3):         {stats['after_line_changes']:>6}\n")
        f.write(f"After keywords:                   {stats['after_keywords']:>6}\n")
        f.write(f"After boundary operators:         {stats['after_boundary_ops']:>6}\n")
        f.write(f"After context (loops/arrays):     {stats['after_context']:>6}\n")
        f.write(f"After file types (.c/.h):         {stats['after_file_types']:>6}\n")
        f.write(f"After exclude noise:              {stats['after_exclude_noise']:>6}\n")
        f.write(f"After size constraints:           {stats['after_size_constraints']:>6}\n")
        f.write(f"\nFINAL FILTERED COMMITS:           {stats['final']:>6}\n")
        
        reduction = (1 - stats['final'] / stats['total']) * 100
        f.write(f"\nReduction: {reduction:.1f}%\n")
        f.write("=" * 60 + "\n")


def save_samples(commits: List[Dict[str, Any]], output_path: str, n: int = 5):
    """Save sample commits for manual review."""
    samples = commits[:min(n, len(commits))]
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"SAMPLE COMMITS (First {len(samples)})\n")
        f.write("=" * 80 + "\n\n")
        
        for i, commit in enumerate(samples, 1):
            f.write(f"\n{'=' * 80}\n")
            f.write(f"SAMPLE {i}/{len(samples)}\n")
            f.write(f"{'=' * 80}\n\n")
            f.write(f"SHA:     {commit['sha']}\n")
            f.write(f"Author:  {commit['author']}\n")
            f.write(f"Date:    {commit['date']}\n")
            f.write(f"Subject: {commit['subject']}\n\n")
            f.write(f"Files changed: {commit['num_files_changed']}\n")
            f.write(f"LOC added:     {commit['loc_added']}\n")
            f.write(f"LOC removed:   {commit['loc_removed']}\n")
            f.write(f"Total LOC:     {commit['total_loc']}\n\n")
            f.write("DIFF:\n")
            f.write("-" * 80 + "\n")
            f.write(commit['diff'][:1000])  # First 1000 chars
            if len(commit['diff']) > 1000:
                f.write("\n... [truncated] ...\n")
            f.write("\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------


def main():
    t0 = datetime.now()
    log.info("=" * 60)
    log.info("SQuire: Filter Commits for Off-by-One Errors")
    log.info("=" * 60)
    
    # Load raw commits
    input_path = os.path.join(RAW_DIR, INPUT_FILE)
    log.info(f"Loading commits from: {input_path}")
    
    with open(input_path, "r", encoding="utf-8") as f:
        commits = json.load(f)
    
    log.info(f"Loaded {len(commits)} commits")
    
    # Apply filters
    filtered_commits, stats = apply_filters(commits)
    
    # Create output directory
    os.makedirs(FILTERED_DIR, exist_ok=True)
    
    # Save filtered commits
    output_path = os.path.join(FILTERED_DIR, OUTPUT_FILE)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(filtered_commits, f, indent=2)
    log.info(f"Saved {len(filtered_commits)} filtered commits to: {output_path}")
    
    # Save statistics
    stats_path = os.path.join(FILTERED_DIR, STATS_FILE)
    save_stats(stats, stats_path)
    log.info(f"Saved statistics to: {stats_path}")
    
    # Save samples
    sample_path = os.path.join(FILTERED_DIR, SAMPLE_FILE)
    save_samples(filtered_commits, sample_path, CONFIG["sample_size"])
    log.info(f"Saved {min(CONFIG['sample_size'], len(filtered_commits))} sample commits to: {sample_path}")
    
    dt = (datetime.now() - t0).total_seconds()
    log.info(f"Completed in {dt:.1f}s")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
