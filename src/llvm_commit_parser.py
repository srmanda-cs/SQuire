#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llvm_commit_parser.py  (Clang‑only version)
-------------------------------------------------------------
• Reads all_v5.16_to_v5.17.json
• Extracts changed hunks and checks out before/after code
• Runs clang -Xclang -ast-dump=json for each snippet
• Captures structural operator / keyword changes
"""

import os, re, json, subprocess, tempfile
from tqdm import tqdm
from datetime import datetime

# ------------------------------------------------------------
INFILE  = "mined_patches_raw/all_v5.16_to_v5.17.json"
OUTFILE = "mined_patches_curated/all_v5.16_to_v5.17_structured.json"
SAMPLE  = 200
CLANG   = "clang"
TMP_DIR = tempfile.gettempdir()
LOGFILE = "parser_diagnostics.log"

# ------------------------------------------------------------
def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    with open(LOGFILE, "a") as f:
        f.write(f"[{ts}] {msg}\n")

def extract_hunks(diff):
    """Robust unified‑diff parser."""
    pat = re.compile(
        r"diff --git a/(.*?) b/(.*?)\r?\n(?:.*\n)*?@@ -(\d+),?\d* \+(\d+),?\d* @@",
        re.MULTILINE,
    )
    return pat.findall(diff)

def git_show(repo, sha, path):
    """Return file text at given commit SHA."""
    try:
        return subprocess.check_output(
            ["git", "-C", repo, "show", f"{sha}:{path}"],
            stderr=subprocess.DEVNULL).decode("utf-8", "ignore")
    except subprocess.CalledProcessError:
        return ""

def snippet(src, line, radius=30):
    lines = src.splitlines()
    return "\n".join(lines[max(line - radius, 0):min(line + radius, len(lines))])

def ast_tokens_clang(src):
    """Run clang AST dump and extract tokens / operators."""
    tmp = os.path.join(TMP_DIR, "llvm_patch_temp.c")
    with open(tmp, "w") as f: 
        f.write(src)
    try:
        out = subprocess.check_output(
            [CLANG, "-Xclang", "-ast-dump=json", "-fsyntax-only", tmp],
            stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return []
    # Basic keyword/operator detection
    text = out.decode("utf-8", "ignore")
    ops  = re.findall(r'"(<|<=|>|>=|==|!=|&&|\|\|)"', text)
    stmts = re.findall(r'"kind": ?"(\w+Stmt)"', text)
    return sorted(set(ops + stmts))

# ------------------------------------------------------------
def process_commit(commit):
    repo  = commit["repo_path"]
    sha   = commit["sha"]
    parent= commit["parent"]
    diff  = commit.get("diff","")
    hunks = extract_hunks(diff)
    if not hunks:
        log(f"⚠️  No diff hunks in {sha[:8]}")
        return []

    out = []
    for pathA, pathB, old_, new_ in hunks:
        path = pathB or pathA
        before = git_show(repo, parent, path)
        after  = git_show(repo, sha, path)
        if not before or not after:
            log(f"🚫 Missing file {path} @ {sha[:8]}")
            continue

        before_fn = snippet(before, int(old_))
        after_fn  = snippet(after,  int(new_))
        before_ast = ast_tokens_clang(before_fn)
        after_ast  = ast_tokens_clang(after_fn)

        if not before_ast and not after_ast:
            log(f"⚠️  Empty AST for {path} ({sha[:8]})")
            continue

        out.append({
            "sha": sha,
            "file": path,
            "loc_added": commit["loc_added"],
            "loc_removed": commit["loc_removed"],
            "before_nodes": before_ast,
            "after_nodes": after_ast,
            "added_nodes": sorted(set(after_ast) - set(before_ast)),
            "removed_nodes": sorted(set(before_ast) - set(after_ast)),
            "contains_bound_ops": commit["contains_bound_ops"],
        })
    return out

# ------------------------------------------------------------
def main():
    open(LOGFILE, "w").close()
    commits = json.load(open(INFILE))
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    structured = []

    for i, c in enumerate(tqdm(commits[:SAMPLE], desc="Parsing via Clang AST")):
        if c.get("is_merge"):
            continue
        try:
            structured += process_commit(c)
        except Exception as e:
            log(f"❌ {c.get('sha','?')[:8]}: {e}")

    json.dump(structured, open(OUTFILE, "w"), indent=2)
    log(f"✅ Done. {len(structured)} structured entries → {OUTFILE}")

# ------------------------------------------------------------
if __name__ == "__main__":
    main()