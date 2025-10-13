#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mine_all_commits.py
-------------------
Collect *all* commits in a Linux kernel tag range, extract subject, body,
author, diff, and basic LOC stats, and store as a single JSON file.
"""

import os
import re
import json
import subprocess
import logging
from datetime import datetime
from typing import List, Dict, Any
from tqdm import tqdm

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

LINUX_REPO = os.path.join(os.path.dirname(__file__), "..", "linux")
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "mined_patches_raw")

TAG_START = "v5.16"
TAG_END = "v5.17"

MAX_TOTAL_LOC = 1000  # truncate large diffs for sanity

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mine_all_commits")

# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------


def git(args: List[str], cwd: str = LINUX_REPO) -> str:
    """Run a git command in the Linux repo and return stdout."""
    result = subprocess.run(
        ["git", "-C", cwd] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def get_commits(start_tag: str, end_tag: str) -> List[str]:
    """Return list of commit SHAs between two tags (newest first)."""
    log.info(f"Collecting commits {start_tag}..{end_tag} …")
    out = git(["log", f"{start_tag}..{end_tag}", "--pretty=%H"])
    commits = out.splitlines()
    log.info(f"Found {len(commits)} commits in range.")
    return commits


def extract_one(sha: str) -> Dict[str, Any]:
    """Extract metadata, stats, and diff for one commit."""

    # --- core metadata ---
    parent = git(["rev-parse", f"{sha}^"]).strip()
    parents = git(["rev-list", "--parents", "-n", "1", sha]).split()[1:]
    author = git(["show", "-s", "--format=%an", sha]).strip()
    email = git(["show", "-s", "--format=%ae", sha]).strip()
    date = git(["show", "-s", "--format=%ad", sha]).strip()
    subject = git(["show", "-s", "--format=%s", sha]).strip()
    body = git(["show", "-s", "--format=%b", sha]).strip()

    # --- diff & file list ---
    diff = git(["show", sha, "--patch", "--no-color"])
    files = [m[1] for m in re.findall(r"diff --git a/(.*?) b/(.*?)\n", diff)]
    num_files = len(files)

    add_count = sum(
        1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")
    )
    del_count = sum(
        1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")
    )
    total_loc = add_count + del_count

    diff_truncated = False
    if total_loc > MAX_TOTAL_LOC:
        diff_truncated = True
        diff = "\n".join(diff.splitlines()[:MAX_TOTAL_LOC]) + "\n... [truncated]"

    # --- quick heuristics ---
    diff_lower = diff.lower()
    contains_loop = any(k in diff_lower for k in ["for(", "while("])
    contains_pointer = "*" in diff or "->" in diff
    contains_bound = any(k in diff for k in ["<=", ">=", "<", ">"])

    tags = []
    if re.search(r"off.?by.?one", subject, re.I):
        tags.append("off-by-one")
    if contains_bound:
        tags.append("bounds")
    if contains_loop:
        tags.append("loop")

    return {
        "sha": sha,
        "parent": parent,
        "parents": parents,
        "author": author,
        "email": email,
        "date": date,
        "subject": subject,
        "body": body,
        "diff": diff,
        "files_changed": files,
        "num_files_changed": num_files,
        "loc_added": add_count,
        "loc_removed": del_count,
        "total_loc": total_loc,
        "diff_truncated": diff_truncated,
        "patch_size_bytes": len(diff.encode("utf-8")),
        "is_merge": len(parents) > 1,
        "is_revert": subject.lower().startswith("revert"),
        "tags": tags,
        "contains_loop_keywords": contains_loop,
        "contains_pointer_ops": contains_pointer,
        "contains_bound_ops": contains_bound,
        "repo_path": LINUX_REPO,
        "tag_start": TAG_START,
        "tag_end": TAG_END,
    }


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------


def main():
    t0 = datetime.now()
    log.info("========== SQuire: Mine ALL Commits ==========")
    log.info(f"Repo: {LINUX_REPO}")
    log.info(f"Range: {TAG_START} → {TAG_END}")

    commits = get_commits(TAG_START, TAG_END)
    mined: list[dict[str, Any]] = []

    out_path = os.path.join(RAW_DIR, f"all_{TAG_START}_to_{TAG_END}.json")
    os.makedirs(RAW_DIR, exist_ok=True)

    with tqdm(total=len(commits), desc="Mining commits", unit="commit") as pbar:
        for sha in commits:
            try:
                data = extract_one(sha)
                if data["subject"].startswith("Merge"):
                    pbar.update(1)
                    continue
                mined.append(data)
            except Exception as e:
                log.warning(f"⚠️  Failed {sha[:8]}: {e}")
            pbar.update(1)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(mined, f, indent=2)

    dt = (datetime.now() - t0).total_seconds()
    log.info(f"✅ Saved {len(mined)} commits → {out_path}")
    log.info(f"Completed in {dt:.1f}s")
    log.info("===============================================")


if __name__ == "__main__":
    main()