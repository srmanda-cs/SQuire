# 🧠 SQuire (Trainee KNighter)

**Team:** Chinmay Dalal & Snehashish Reddy Manda  
**Course:** COMP790‑199  
**Proposal Type:** Systems Research Project  

---

## 🌟 Overview

**SQuire** is an exploration into how **Large Language Models (LLMs)** can help automatically **synthesize static analysis checkers** — the tools that detect bugs in large codebases like the Linux kernel.

Traditional static analyzers are often hand‑written, expensive to maintain, and limited to predefined bug patterns. Our aim is to see if LLMs can learn bug patterns directly from historical bug‑fix patches, generate targeted static checkers, and refine them over time — **scalable, explainable, and grounded in real‑world bug knowledge**.

In short:

> **Instead of using LLMs to scan code directly, we use them to create the tools that do.**

---

## 🏗️ Background

Our idea is inspired by the **KNighter (SOSP ’25)** paper, which demonstrated an LLM‑driven approach to synthesizing static checkers from bug‑fix patches. KNighter’s framework — *pattern → plan → checker → validate → refine* — successfully found **92 kernel bugs (including 30 CVEs)**.

However, the KNighter system generalized across both simple and complex fixes, reducing precision and effectiveness in simpler cases.  

**SQuire (“Trainee KNighter”)** narrows the focus:

- We target **simple, intra‑procedural fixes** (e.g., null dereference after allocation, missing error checks).  
- We aim to develop a **confidence self‑reporting system** within the LLM, providing insight into how “sure” it is about a generated checker.  

---

## ⚙️ Approach

We’re building a pipeline that looks like this:

1. **Patch Mining** → gather relevant Linux kernel bug‑fix patches  
2. **Pattern Extraction** → LLM identifies the underlying bug pattern  
3. **Rule Synthesis** → LLM emits **Coccinelle (Spatch)** rules  
4. **Validation & Refinement** → run those rules on historical snapshots, measure accuracy, and refine  
5. **(Optional)** → port validated checkers to **Smatch / CodeQL**

We use **Gemini 2.5‑Flash** as our main agent (chosen for performance and cost balance).  

---

## 📊 Scope & Metrics

- **Target bug types:** 8–12 simple, intra‑procedural patterns  
- **Dataset:** Linux kernel  
  - Train ≤ v5.17  
  - Tune v5.18–v6.1  
  - Test v6.2–v6.8  
- **Goals:**  
  - Precision (top‑50 findings per checker): **≥ 60–75 %**  
  - Runtime per kernel tree: **≤ 30 min**  
  - Recover **≥ 20–30 %** of known historical fixes  
  - Confidence score correlates with correctness *(Spearman ≥ 0.3)*  

**Baselines:** Smatch or minimal hand‑written Coccinelle scripts  
**Deliverables:** generated checkers, mined patch dataset, evaluation table, 10–20 verified true positives, and a brief disclosure plan.  

---

## 👥 Roles & Milestones

We work in **rotating leads** for total exposure and balance:  

| Phase | Chinmay | Snehashish |
|-------|----------|------------|
| **Pre‑Milestone** | Checker engineering (rule design, integration) | LLM pipeline (prompts, synthesis, confidence) |
| **Post‑Milestone** | LLM tuning & prompt iteration | Checker refinement |
| **Always Shared** | Patch mining, evaluation, triage, presentation |  |

---

## 🚀 Current Status

- ✅ LLM agent selected (Gemini 2.5‑Flash)  
- ✅ Initial bug class list finalized  
- 🔄 Mining historical patches  
- 🔧 Setting up Coccinelle rule synthesis pipeline  
- 🧩 Planning evaluation metrics and refinement loop  

---

## 💭 Why It Matters

Software reliability in large, evolving systems like the Linux kernel depends on **catching simple bugs early**.  
By training LLMs to encode these patterns as first‑class static checkers, we aim to **extend the reach of automated code reasoning tools** — faster, updatable, and explainable.  

---

## 📘 References

- Yang, C., Zhao, Z., Xie, Z., Li, H., & Zhang, L. (2025). *KNighter: Transforming Static Analysis with LLM‑Synthesized Checkers.*  
  _Proceedings of the ACM SIGOPS 31st Symposium on Operating Systems Principles (SOSP '25)_.  
  Association for Computing Machinery, New York, NY, USA.  
  [https://doi.org/10.1145/3731569.3764827](https://doi.org/10.1145/3731569.3764827)

**BibTeX:**
```bibtex
@inproceedings{knighter,
    title     = {KNighter: Transforming Static Analysis with LLM-Synthesized Checkers},
    author    = {Yang, Chenyuan and Zhao, Zijie and Xie, Zichen and Li, Haoyu and Zhang, Lingming},
    year      = {2025},
    publisher = {Association for Computing Machinery},
    address   = {New York, NY, USA},
    url       = {https://doi.org/10.1145/3731569.3764827},
    doi       = {10.1145/3731569.3764827},
    booktitle = {Proceedings of the ACM SIGOPS 31st Symposium on Operating Systems Principles},
    location  = {Seoul, Republic of Korea},
    series    = {SOSP '25}
}
```

Other resources:
- Linux Kernel Git History  
- Coccinelle & Smatch Documentation  

---

## 🧩 Keywords

```
LLM • Static Analysis • Bug Detection • Coccinelle • Smatch • Gemini 2.5‑Flash • Linux Kernel • AI‑Assisted Tooling
```

---

## 🪪 License

This project, **SQuire (Trainee KNighter)**, is licensed under the **Apache License 2.0**.  
You are free to use, modify, and distribute this work under the terms of the license, provided that proper attribution is given and a copy of the license is included.

See the [LICENSE](./LICENSE) file for full details.

```
Copyright 2025 Chinmay Dalal and Snehashish Reddy Manda

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at:

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied.
See the License for the specific language governing permissions and limitations under the License.
```

---

# Project Setup
1. Ensure you are on a Linux distro and ensure you have Python, gcc/g++, coccinelle (spatch) all installed before proceeding with any of the setup.
2. Clone the repository and initialize submodules
   ```bash
   git clone https://github.com/srmanda-cs/SQuire.git
   cd SQuire

   git submodule update --init --recursive
   ```
3. Setup a Python virtual environment
   ```bash
    python -m venv .venv
    source .venv/bin/activate
   ```
4. Install the project requirements
   ```bash
    pip install -r requirements.txt
    ```
5. Create a file in the root directory called: .env which would look as follows
   ```
    API_KEY=<your_openai_compatible_api_key>
    BASE_URL=<your_openai_compatible_base_url>
    LLM_MODEL=<your_chosen_model_name>
   ```
6. Run test_llm_response.py inside test/openai_api and make sure you're getting a response back
7. Run test_rules.cocci inside test/coccinelle using the following command from the root directory:
   ```bash
    spatch test/coccinelle/test_rules.cocci test/coccinelle/test_bugs.c
   ```
8. You should see the following output:
    ```bash
    init_defs_builtins: /usr/lib/ocaml/coccinelle/standard.h
    HANDLING: test/coccinelle/test_bugs.c
    Possible unsafe use of malloc'ed variable: ptr at line 9
    ```
9. If all tests so far are successful, then it means everything is working! (for now at least...)