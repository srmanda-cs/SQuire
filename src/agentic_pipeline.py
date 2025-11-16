#!/usr/bin/env python3
"""
agentic_pipeline.py
-------------------
From curated Null‑Pointer‑Dereference commits → synthesized Clang Static Analyzer (CSA) checker.

Stages:
1. Extract per-commit bug patterns using LLM
2. Merge all patterns into one canonical rule
3. Synthesize a high‑level detection plan
4. Generate a runnable `GeneratedNPDChecker.cpp` source file
"""

import os, json, sys, re
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_DIR = BASE_DIR / "prompts"
CURATED_FILE = BASE_DIR / "mined_patches_curated" / "v5.10_to_v5.17_curated.json"

load_dotenv(BASE_DIR / ".env")

API_KEY   = os.getenv("API_KEY")
BASE_URL  = os.getenv("BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

if not API_KEY:
    sys.exit("❌ Missing API_KEY in .env")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def ask_llm(prompt: str, temperature: float = 0.15) -> str:
    """Single call wrapper for the OpenAI model."""
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    result = resp.choices[0].message.content.strip()
    result = re.sub(r"^```[\w-]*|```$", "", result, flags=re.MULTILINE).strip()
    return result

def read_prompt(name: str) -> str:
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        sys.exit(f"❌ Missing prompt: {path}")
    return path.read_text(encoding="utf-8")

def log(msg: str):
    print(f"[agentic] {msg}")

# ---------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------
def extract_patterns(curated_json):
    tmpl = read_prompt("pattern_extraction")
    patterns = []
    for p in curated_json.get("Null-Pointer Dereference (NPD)", []):
        diff = p.get("diff", "")
        msg  = p.get("message", "")
        prompt = tmpl.replace("{{DIFF_AND_MESSAGE}}", msg + "\n\n" + diff)
        log(f"→ Extracting pattern from commit {p['commit'][:8]}")
        patterns.append(ask_llm(prompt))
    return patterns

def merge_patterns(patterns):
    tmpl = read_prompt("pattern_merge")
    joined = "\n".join(f"- {p}" for p in patterns)
    prompt = tmpl.replace("{{BUG_PATTERNS}}", joined)
    log("→ Merging extracted patterns")
    return ask_llm(prompt)

def synthesize_plan(merged_pattern):
    tmpl = read_prompt("plan_synthesis")
    prompt = tmpl.replace("{{BUG_PATTERN}}", merged_pattern)
    log("→ Synthesizing checker plan")
    return ask_llm(prompt)

def sanitize_cpp_for_llvm20(code: str) -> str:
    """Quick patch for legacy LLVM API calls in generated code."""
    fixes = {
        ".equals(": " == ",
        ".equals_insensitive(": " == ",   # fallback
        ".startswith(": ".starts_with(",
        ".endswith(": ".ends_with("
    }
    for old, new in fixes.items():
        code = code.replace(old, new)

    # Replace Optional<> with std::optional<>
    code = re.sub(r"\bOptional<", "std::optional<", code)

    # Fix legacy Checker<> callback syntax if model reverts to older API
    code = re.sub(r"\bcheckPostCall\b", "check::PostCall", code)
    code = re.sub(r"\bcheckPreStmt\b", "check::PreStmt<Expr>", code)
    code = re.sub(r"\bcheckDeadSymbols\b", "check::DeadSymbols", code)

    # Fix incorrect emitReport() calls (raw pointer → std::move)
    code = re.sub(r"C\.emitReport\((\w+)\);", r"C.emitReport(std::move(\1));", code)

    # If missing, inject required CallEvent include
    if 'CallEvent.h' not in code:
        code = '#include "clang/StaticAnalyzer/Core/PathSensitive/CallEvent.h"\n' + code

    return code

def generate_checker(merged_pattern, plan_text):
    tmpl = read_prompt("checker_generation")
    llvm_env_info = """
    # ENVIRONMENT CONTEXT
    - LLVM/Clang Version: 20.1.8
    - Platform: Manjaro Linux (x86_64)
    - Include root for Clang Static Analyzer: /usr/include
    - Required headers exist under:
      /usr/include/clang/StaticAnalyzer/Core/
      /usr/include/clang/StaticAnalyzer/Frontend/
    - Registry header is located at:
      /usr/include/clang/StaticAnalyzer/Frontend/CheckerRegistry.h
    - Build command to test compilation:
      clang++ -fPIC -shared -fno-rtti -std=c++17 -I/usr/include GeneratedNPDChecker.cpp -o libNPDChecker.so
    """

    prompt = (tmpl.replace("{{BUG_PATTERN}}", merged_pattern)
                   .replace("{{PLAN_TEXT}}", plan_text)
                   + "\n\n" + llvm_env_info)

    log("→ Requesting C++ CSA checker code generation")
    cpp_code = ask_llm(prompt)
    cpp_code = re.sub(r"^```[\w-]*|```$", "", cpp_code, flags=re.MULTILINE).strip()

    cpp_code = sanitize_cpp_for_llvm20(cpp_code)

    if "class" not in cpp_code or "Checker<" not in cpp_code:
        log("⚠️ Possible invalid checker; please inspect manually.")

    out_file = Path("GeneratedNPDChecker.cpp")
    out_file.write_text(cpp_code, encoding="utf-8")
    log(f"✅ Generated and saved → {out_file}")
    return cpp_code

# ---------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------
def main():
    log("Loading curated JSON dataset …")
    curated = json.loads(Path(CURATED_FILE).read_text(encoding="utf-8"))

    # Stage 1 -----------------------------------------------------------
    patterns = extract_patterns(curated)
    Path("pattern_outputs.txt").write_text("\n\n".join(patterns))
    log("🧩 Stored raw patterns → pattern_outputs.txt")

    # Stage 2 -----------------------------------------------------------
    merged = merge_patterns(patterns)
    Path("merged_pattern.txt").write_text(merged)
    log("🔗 Stored merged pattern → merged_pattern.txt")

    # Stage 3 -----------------------------------------------------------
    plan = synthesize_plan(merged)
    Path("checker_plan.txt").write_text(plan)
    log("🧠 Stored checker plan → checker_plan.txt")

    # Stage 4 -----------------------------------------------------------
    code = generate_checker(merged, plan)
    log("🎯 C++ checker code ready.")

    # Summary -----------------------------------------------------------
    print("\n=== PIPELINE SUMMARY ===")
    print(f"Patterns extracted: {len(patterns)}")
    print(f"Merged rule preview: {merged[:140]} …")
    print(f"Plan length: {len(plan.split())} words")
    print(f"Output: GeneratedNPDChecker.cpp")
    print("===========================")

# ---------------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Interrupted by user.")