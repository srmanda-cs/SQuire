# 🧠 SQuire (Trainee KNighter)

**Team:** Chinmay Dalal & Snehashish Reddy Manda  
**Course:** COMP790‑199  
**Proposal Type:** Systems Research Project

---

## 🌟 Overview

**SQuire** is an exploration into how **Large Language Models (LLMs)** can help automatically **synthesize static analysis checkers** — the tools that detect bugs in large codebases like the Linux kernel.

Traditional static analyzers are often hand‑written, expensive to maintain, and limited to predefined bug patterns. Our aim is to see if LLMs can learn bug patterns directly from historical bug‑fix patches, generate targeted static checkers, and refine them over time – **scalable, explainable, and grounded in real‑world bug knowledge**.

In short:

> **Instead of using LLMs to scan code directly, we use them to create the tools that do.**

---

## 🏗️ Background

Our idea is inspired by the **KNighter (SOSP ’25)** paper, which demonstrated an LLM‑driven approach to synthesizing static checkers from bug‑fix patches. KNighter’s framework — _pattern → plan → checker → validate → refine_ — successfully found **92 kernel bugs (including 30 CVEs)**.

However, the KNighter system generalized across both simple and complex fixes. That reduced the precision and clarity of checkers for simpler bugs.

**SQuire (“Trainee KNighter”)** narrows the focus:

- We target **simple, intra‑procedural fixes** (e.g., null dereference after allocation, missing error checks).
- We aim to develop a **confidence self‑reporting** system within the LLM, providing insight into how “sure” it is about a generated checker.

---

## ⚙️ Approach

We’re building a pipeline that looks like this:

1. **Patch Mining** → Gather relevant Linux kernel bug‑fix patches
2. **Pattern Extraction** → LLM identifies the underlying bug pattern
3. **Rule Synthesis** → LLM outputs **Coccinelle (Spatch)** rules
4. **Validation & Refinement** → Run those rules on historical snapshots, measure accuracy, and refine
5. **(Optional)** → Port validated checkers to **Smatch/CodeQL**

We use **Gemini 2.5‑Flash** as our main agent (chosen for performance and cost balance).

---

## 📊 Scope & Metrics

- **Target bug types:** 8–12 simple, intra‑procedural patterns
- **Dataset:** Linux kernel
  - Train ≤ v5.17
  - Tune on v5.18–v6.1
  - Test on v6.2–v6.8
- **Goals:**
  - Precision (top‑50 findings per checker): **≥ 60–75%**
  - Runtime per kernel tree: **≤ 30 min**
  - Recover **≥ 20–30%** of known historical fixes
  - Confidence score **correlates with correctness (Spearman ≥ 0.3)**

**Baselines:** Smatch or minimal hand‑written Coccinelle scripts  
**Deliverables:**  
Generated checkers, mined patch dataset, evaluation table, ~10–20 verified true positives, and a short disclosure plan.

---

## 👥 Roles & Milestones

We work in **rotating leads** for total exposure and balance:

| Phase              | Chinmay                                        | Snehashish                                    |
| ------------------ | ---------------------------------------------- | --------------------------------------------- |
| **Pre‑Milestone**  | Checker engineering (rule design, integration) | LLM pipeline (prompts, synthesis, confidence) |
| **Post‑Milestone** | LLM tuning & prompt iteration                  | Checker refinement                            |
| **Always Shared**  | Patch mining, evaluation, triage, presentation |

---

## 🚀 Current Status

- ✅ LLM agent selected (Gemini 2.5‑Flash)
- ✅ Initial bug class list finalized
- 🔄 Mining historical patches
- 🔧 Setting up Coccinelle rule synthesis pipeline
- 🧩 Planning evaluation metrics and refinement loop

---

## 💭 Why It Matters

Software reliability in large, evolving systems like the Linux kernel depends on **catching simple bugs** early and efficiently.  
By training LLMs to encode these patterns as first‑class static checkers, we aim to **extend the reach of automated code reasoning tools** — faster, updatable, and explainable.

---

## 📘 References

- _KNighter: Learning Static Checkers from Bug‑Fix Patches_, SOSP 2025
- Linux Kernel Git History
- Coccinelle & Smatch Documentation

---

## 🧩 Keywords

```
LLM • Static Analysis • Bug Detection • Coccinelle • Smatch • Gemini 2.5‑Flash • Linux Kernel • AI‑Assisted Tooling
```
