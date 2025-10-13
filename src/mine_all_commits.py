#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mine_all_commits.py
-------------------
Collect *all* commits in a Linux kernel tag range, extract subject, body,
author, diff, and basic LOC stats, and store as a single JSON file.

This version does NO keyword filtering, NO bug-class grouping.
Used as the first stage before semantic filtering (e.g., MiniLM).

Usage:
    python3 src/mine_all_commits.py
"""

import os, json, subprocess, logging
from datetime import datetime
from typing import List, Dict, Any

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

LINUX_REPO = os.path.join(os.path.dirname(__file__), "..", "linux")
RAW_DIR    = os.path.join(os.path.dirname(__file__), "..", "mined_patches_raw")

TAG_START  = "v5.16"
TAG_END    = "v5.17"

MAX_TOTAL_LOC = 1000    # optional safety cap, large patches truncated
SAVE_EVERY    = 500     # commits between progress reports

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
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
    """Extract metadata and diff for one commit."""
    fmt = "%H%n%an%n%ad%n%s%n%b"
    raw = git(["show", sha, f"--pretty=format:{fmt}", "--patch", "--no-color"])
    lines = raw.splitlines()

    def pop_line():
        return lines.pop(0).strip() if lines else ""

    sha_line = pop_line()
    author   = pop_line()
    date     = pop_line()
    subject  = pop_line()

    # find start of diff
    diff_idx = next((i for i, l in enumerate(lines) if l.startswith("diff --git")), len(lines))
    body = "\n".join(lines[:diff_idx]).strip()
    diff = "\n".join(lines[diff_idx:])

    add_count = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    del_count = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    total_loc = add_count + del_count

    if total_loc > MAX_TOTAL_LOC:
        diff = "\n".join(diff.splitlines()[:MAX_TOTAL_LOC]) + "\n... [truncated]"

    return {
        "sha": sha_line,
        "author": author,
        "date": date,
        "subject": subject,
        "body": body,
        "loc_added": add_count,
        "loc_removed": del_count,
        "diff": diff,
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
    mined = []

    for i, sha in enumerate(commits, start=1):
        try:
            data = extract_one(sha)
            # skip merges — they’re mostly noise for bug‑fix training
            if data["subject"].startswith("Merge"):
                continue
            mined.append(data)
        except Exception as e:
            log.warning(f"⚠️  Failed {sha[:8]}: {e}")
        if i % SAVE_EVERY == 0:
            log.info(f"Processed {i}/{len(commits)} commits …")

    out_path = os.path.join(RAW_DIR, f"all_{TAG_START}_to_{TAG_END}.json")
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(mined, f, indent=2)

    dt = (datetime.now() - t0).total_seconds()
    log.info(f"✅ Saved {len(mined)} commits → {out_path}")
    log.info(f"Completed in {dt:.1f}s")
    log.info("===============================================")


if __name__ == "__main__":
    main()