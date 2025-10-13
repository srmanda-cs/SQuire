#!/usr/bin/env python3
"""
src/filter_commits.py
---------------------

Stage 1: Traverse Linux kernel history between v5.10–v5.17,
filter commits that modify only a few lines (1–5 added + deleted)
and aren’t merge/mega commits, cosmetic, or non‑C code.

Stage 2: Run lightweight keyword‑based pattern matching
to bucket commits under seven bug categories
listed in src/bug_categories.json.

Output:
    mined_patches_raw/v5.10_to_v5.17_categorized.json
Each key = category → list of commits.

Dependencies:
    pip install gitpython tqdm
"""

import os
import json
import re
from git import Repo
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
LINUX_PATH = os.path.join(BASE_DIR, "linux")
OUTPUT_PATH = os.path.join(BASE_DIR, "mined_patches_raw")
OUTPUT_FILE = os.path.join(OUTPUT_PATH, "v5.10_to_v5.17_categorized.json")
CATEGORIES_FILE = os.path.join(BASE_DIR, "src", "bug_categories.json")

START_TAG = "v5.10"
END_TAG = "v5.17"

MAX_LINES_CHANGED = 5     # additions + deletions
MAX_FILES_CHANGED = 2     # maximum number of files per commit
ALLOWED_FILE_EXT = (".c", ".h")

TRIVIAL_WORDS = (
    "typo", "style", "indent", "format", "refactor", "rename",
    "comment", "documentation", "doc", "docs", "whitespace",
    "spelling", "reword", "update copyright"
)

# ---------------------------------------------------------------------------
# Keyword heuristics per category
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS = {
    "Null-Pointer Dereference (NPD)": [
        r"\bnull\b", r"== *NULL", r"!= *NULL", r"kmalloc",
        r"kzalloc", r"devm_kzalloc", r"\bptr\b", r"!.*ptr"
    ],
    "Use-Before-Intialization (UBI)": [
        r"uninit", r"initialize", r"= *NULL", r"= *0",
        r"memset", r"set to 0", r"init"
    ],
    "Integer Overflow": [
        r"overflow", r"INT_MAX", r"UINT_MAX", r"size_t",
        r"< *0", r">\s*INT_MAX", r"return -EINVAL"
    ],
    "Out-of-Bounds (OOB)": [
        r"\bindex\b", r"len", r"size", r"count",
        r"< *len", r">= *len", r"< *size", r">= *size", r"BUFFER_SIZE"
    ],
    "Buffer Overflow": [
        r"memcpy", r"memmove", r"strcpy", r"strncpy",
        r"copy_from_user", r"copy_to_user", r"sizeof",
        r"min\s*\(.*len", r"buf\["
    ],
    "Memory Leak": [
        r"free", r"kfree", r"release", r"cleanup",
        r"goto err", r"put_device", r"return"
    ],
    "Double Free": [
        r"free", r"kfree", r"ptr = NULL", r"if *\(.*!.*\)"
    ],
}

# ---------------------------------------------------------------------------

os.makedirs(OUTPUT_PATH, exist_ok=True)

# Load configured categories (to preserve order)
with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
    BUG_CATEGORIES = json.load(f)

# Prepare result dictionary
categorized = {cat: [] for cat in BUG_CATEGORIES}

# Initialize repository
repo = Repo(LINUX_PATH)
assert not repo.bare, f"Repository at {LINUX_PATH} not found or invalid."

# Tag range
start = repo.tags[START_TAG]
end = repo.tags[END_TAG]

commits = list(repo.iter_commits(f"{start.commit.hexsha}..{end.commit.hexsha}", no_merges=True))
print(f"Scanning {len(commits)} commits between {START_TAG} and {END_TAG}...")

filtered = []

# ---------------------------------------------------------------------------
# Stage 1 — Filter small diffs
# ---------------------------------------------------------------------------

for commit in tqdm(commits, desc="Filtering small diffs", ncols=100):
    msg_lower = commit.message.lower()
    if any(word in msg_lower for word in TRIVIAL_WORDS):
        continue

    stats = commit.stats.total
    total_changes = stats["insertions"] + stats["deletions"]
    total_files = stats["files"]

    if total_changes == 0 or total_changes > MAX_LINES_CHANGED:
        continue
    if total_files == 0 or total_files > MAX_FILES_CHANGED:
        continue

    changed_files = [f for f in commit.stats.files.keys() if f.endswith(ALLOWED_FILE_EXT)]
    if not changed_files:
        continue
    if not commit.parents:
        continue

    parent = commit.parents[0]
    try:
        diff_text = repo.git.diff(parent.hexsha, commit.hexsha, unified=3)
    except Exception:
        continue

    entry = {
        "commit": commit.hexsha,
        "parent": parent.hexsha,
        "author": commit.author.name,
        "email": commit.author.email,
        "date": commit.committed_datetime.isoformat(),
        "message": commit.message.strip(),
        "files_changed": changed_files,
        "insertions": stats["insertions"],
        "deletions": stats["deletions"],
        "diff": diff_text,
    }

    filtered.append(entry)

print(f"✅ Stage 1 complete — {len(filtered)} small commits retained")

# ---------------------------------------------------------------------------
# Stage 2 — Keyword-based classification (first match only)
# ---------------------------------------------------------------------------

for commit in tqdm(filtered, desc="Classifying commits", ncols=100):
    text = (commit["message"] + "\n" + commit["diff"]).lower()
    # Stop at first matching category to avoid duplicates
    for cat in BUG_CATEGORIES:
        regexes = CATEGORY_KEYWORDS.get(cat, [])
        if any(re.search(rgx, text) for rgx in regexes):
            categorized[cat].append(commit)
            break

# ---------------------------------------------------------------------------
# Stage 3 — Save final categorized file
# ---------------------------------------------------------------------------

with open(OUTPUT_FILE, "w", encoding="utf-8", errors="replace") as f:
    json.dump(categorized, f, indent=2, ensure_ascii=False)

# Unique commit count sanity check
unique_hashes = {c["commit"] for lst in categorized.values() for c in lst}
print(f"\n✅ Stage 2 complete — {len(unique_hashes)} unique commits auto‑categorized "
      f"across {len(BUG_CATEGORIES)} categories")
print(f"📦 Output → {OUTPUT_FILE}")