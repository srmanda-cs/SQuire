# SQuire Progress Summary

## Project Goal
Implement KNighter's methodology for off-by-one error detection in the Linux kernel using LLM-synthesized static checkers.

## What We've Accomplished

### 1. ✅ Data Collection & Mining (v5.16 → v5.17)
- **Script**: `src/mine_all_commits.py`
- **Result**: Mined 13,076 commits from Linux kernel v5.16 to v5.17
- **Output**: `mined_patches_raw/commits_5.16_to_5.17.json`

### 2. ✅ Intelligent Filtering Pipeline
- **Script**: `src/filter_commits.py`
- **Filters Applied**:
  - Off-by-one keywords (bounds, index, overflow, etc.)
  - Small, focused changes (1-10 LOC)
  - Single file modifications
  - C/C++ files only
  - Excluded documentation/tests
  - Excluded trivial changes (whitespace, comments)
- **Result**: Reduced from 13,076 → **173 high-quality candidates** (98.7% reduction)
- **Output**: `mined_patches_curated/filtered_off_by_one.json`

### 3. ✅ Full Function Context Extraction
- **Script**: `src/extract_functions.py`
- **Methodology**: Following KNighter - extract complete function code (buggy + patched versions)
- **Result**: 
  - 134/173 commits with function context (77.5%)
  - 138 total functions extracted
- **Output**: `mined_patches_curated/commits_with_functions.json`

### 4. ✅ LLM Pattern Analysis Pipeline
- **Script**: `src/analyze_patterns.py`
- **Features**:
  - OpenAI-compatible API integration
  - Structured JSON analysis output
  - Pattern identification
  - Coccinelle feasibility assessment
  - Confidence scoring
- **Status**: Ready to run (needs .env configuration)

## Current Dataset Statistics

```
Original commits (v5.16→v5.17):     13,076
After filtering:                       173  (1.3% retention)
With function context:                 134  (77.5% of filtered)
Total functions extracted:             138
```

## Next Steps

### Immediate (Ready to Execute)

1. **Configure .env file**:
   ```bash
   API_KEY=<your_openai_compatible_api_key>
   BASE_URL=<your_openai_compatible_base_url>
   LLM_MODEL=<your_chosen_model_name>
   ```

2. **Run Pattern Analysis**:
   ```bash
   python src/analyze_patterns.py
   ```
   - Analyzes first 20 commits as test batch
   - Identifies true off-by-one patterns
   - Assesses Coccinelle feasibility

3. **Review Analysis Results**:
   - Check `mined_patches_curated/pattern_analysis.json`
   - Identify high-confidence patterns
   - Select candidates for Coccinelle rule generation

### Phase 2: Coccinelle Rule Generation

4. **Create Rule Generator** (Next script to build):
   - Input: Confirmed off-by-one patterns from LLM analysis
   - Output: Coccinelle (.cocci) rules
   - Validation: Test against original buggy/patched code

5. **Rule Refinement**:
   - Test rules on Linux kernel
   - Measure false positive rate
   - Iterate based on results

### Phase 3: Validation & Evaluation

6. **Checker Validation**:
   - Run on held-out commits (v5.18-v6.1)
   - Measure precision/recall
   - Compare against baselines

7. **Bug Detection**:
   - Scan recent kernel versions (v6.2-v6.8)
   - Triage findings
   - Report true positives

## Key Differences from Original Approach

### What We Changed:
1. **No LLVM parsing** - Using git-based function extraction instead
2. **Focused scope** - Single bug class (off-by-one) for depth
3. **Aggressive filtering** - 98.7% reduction to high-quality candidates
4. **OpenAI-compatible API** - Flexible LLM backend

### Why These Changes:
1. **LLVM complexity** - Git extraction is simpler and sufficient for our needs
2. **Resource constraints** - Deep focus on one pattern vs. shallow coverage of many
3. **Quality over quantity** - Better to have 20 excellent patterns than 200 mediocre ones
4. **Flexibility** - Can use various LLM providers (OpenAI, Anthropic, local models)

## File Structure

```
SQuire/
├── src/
│   ├── mine_all_commits.py      # Initial commit mining
│   ├── filter_commits.py        # Intelligent filtering
│   ├── extract_functions.py     # Function context extraction
│   └── analyze_patterns.py      # LLM pattern analysis
├── mined_patches_raw/
│   └── commits_5.16_to_5.17.json
├── mined_patches_curated/
│   ├── filtered_off_by_one.json
│   ├── commits_with_functions.json
│   └── pattern_analysis.json (to be generated)
└── linux/                       # Kernel repository
```

## Cost Estimation

### LLM Analysis (20 commits):
- Average prompt: ~2,000 tokens
- Average response: ~500 tokens
- Total: ~50,000 tokens
- Cost (GPT-4o-mini): ~$0.01
- Cost (Claude Sonnet): ~$0.15

### Full Dataset (134 commits):
- Estimated: ~335,000 tokens
- Cost (GPT-4o-mini): ~$0.05
- Cost (Claude Sonnet): ~$1.00

**Much more affordable than KNighter's approach!**

## Success Metrics

### Minimum Viable:
- [ ] 10+ confirmed off-by-one patterns identified
- [ ] 5+ Coccinelle rules generated
- [ ] 60%+ precision on top-50 findings

### Stretch Goals:
- [ ] 20+ confirmed patterns
- [ ] 10+ Coccinelle rules
- [ ] 75%+ precision
- [ ] 1+ new bug found in recent kernel

## Blockers & Risks

### Current Blockers:
- None! Ready to proceed with LLM analysis

### Potential Risks:
1. **LLM accuracy** - May misidentify patterns
   - Mitigation: Manual review of high-confidence results
2. **Coccinelle limitations** - Some patterns may not be expressible
   - Mitigation: Focus on feasible patterns first
3. **False positives** - Rules may be too broad
   - Mitigation: Iterative refinement with validation

## Timeline Estimate

- **Week 1**: LLM analysis + pattern validation (current phase)
- **Week 2**: Coccinelle rule generation + testing
- **Week 3**: Refinement + bug hunting
- **Week 4**: Evaluation + documentation

## Questions to Address

1. What LLM model will you use? (GPT-4o, Claude, Gemini, local?)
2. What precision threshold is acceptable? (60%? 75%?)
3. Should we expand to more bug classes after off-by-one?
4. Do we need to compare against Smatch/other tools?

---

**Status**: Ready for LLM pattern analysis phase
**Next Action**: Configure .env and run `python src/analyze_patterns.py`
