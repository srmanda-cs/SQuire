# 🧠 SQuire (Trainee KNighter)

**Team:** Chinmay Dalal & Snehashish Reddy Manda  
**Course:** COMP790‑199  
**Proposal Type:** Systems Research Project  

---

## 🌟 Overview

**SQuire** is an exploration into how **Large Language Models (LLMs)** can help automatically **synthesize static analysis checkers** — the tools that detect bugs in large codebases like the Linux kernel.

Traditional static analyzers are often hand‑written, expensive to maintain, and limited to predefined bug patterns. Our aim is to see if LLMs can learn bug patterns directly from historical bug‑fix patches, generate targeted static checkers (specifically for the **Clang Static Analyzer**), and refine them over time.

In short:

> **Instead of using LLMs to scan code directly, we use them to create the tools that do.**

---

## 🏗️ Background

Our idea is inspired by the **KNighter (SOSP ’25)** paper, which demonstrated an LLM‑driven approach to synthesizing static checkers. While KNighter targeted a broad range of bugs, **SQuire** focuses on **simple, intra‑procedural fixes** (e.g., Null Pointer Dereference, Use-Before-Initialization) to maximize precision and reduce hallucination.

---

## ⚙️ Approach

We have built an end-to-end pipeline:

1. **Patch Mining** (`src/filter_commits.py`) → Gather and curate relevant Linux kernel bug‑fix patches.
2. **Agentic Pipeline** (`src/agentic_pipeline.py`) → An LLM-driven loop that:
   - Extracts the abstract bug pattern.
   - Synthesizes a detection plan.
   - Generates executable C++ code for a Clang Static Analyzer checker.
3. **Validation** → Compile and run the checker against test cases and historical kernel versions.

---

## 🛠️ Project Setup

1. **Prerequisites:** Ensure you are on a Linux distro (Arch/Manjaro recommended for latest LLVM) and have:
   - Python 3.10+
   - Clang/LLVM 20
   - `git`, `make`, `gcc`

2. **Clone & Submodules:**
   ```bash
   git clone https://github.com/srmanda-cs/SQuire.git
   cd SQuire
   git submodule update --init --recursive
   ```

3. **Python Environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Create a `.env` file in the root directory:
   ```env
   API_KEY=<your_openai_compatible_api_key>
   BASE_URL=<your_openai_compatible_base_url>
   LLM_MODEL=<your_chosen_model_name>
   ```

---

## 🏃‍♂️ Running the Pipeline

To run the full agentic loop (Pattern Extraction → Plan → Code Generation):

```bash
python src/agentic_pipeline.py
```

This will read from `mined_patches_curated/`, interact with the LLM, and output a `GeneratedNPDChecker.cpp` file.

---

## 🧪 Smoke Testing

Once a checker has been generated (or using the pre-generated example), you can verify it using our smoke test harness.

**Navigate to the test directory:**
```bash
cd smoke_test/simple_tool
```

**Build the checker:**
```bash
make clean
make
```
*This compiles the C++ checker into a shared object (`libNPDChecker.so`).*

**Run the analysis:**
```bash
clang -Xclang -load -Xclang ./libNPDChecker.so \
      -Xclang -analyze \
      -Xclang -analyzer-checker=squire.NPDChecker \
      test.c
```

**Expected Output:**
You should see a warning pointing to the specific line in `test.c` where the bug exists:
```text
test.c:10:8: warning: Result of a possibly failing allocation or metadata access is used without a preceding NULL check [squire.NPDChecker]
   10 |     *p = 42;
      |     ~~ ^
```

---

## 👥 Roles

| Member | Responsibilities |
|--------|------------------|
| **Chinmay Dalal** | Kernel infrastructure, Tooling (LLVM/Clang), Checker Refinement |
| **Snehashish Reddy** | LLM Pipeline (Prompts, Agentic Loop), Project Vision, Smoke Testing |

---

## 📘 References

- Yang, C., et al. (2025). *KNighter: Transforming Static Analysis with LLM‑Synthesized Checkers.* SOSP '25.

## 🪪 License

**Apache License 2.0**. See [LICENSE](./LICENSE).
