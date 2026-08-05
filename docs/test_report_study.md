## Study Agents — Primary Test Report

### Scope

- Flashcards Agent + Study Plan Agent + Revision Agent end-to-end (mock-mode)
- Grounding (topic allow-list) + invented-topic blocking
- Human-review gate (needs_human_review + export gate)
- Batch generation + deterministic evaluation metrics

### Evidence Bundle (raw logs)

- E2E report: [study_lane_e2e_2026-08-02.md](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/study_lane_e2e_2026-08-02.md)
- Pytest output: [pytest_features_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/pytest_features_2026-08-02.txt)
- Batch run output: [study_batch_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/study_batch_2026-08-02.txt)
- Invented-topic repro output: [invented_topics_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/invented_topics_2026-08-02.txt)
- Review/export gate repro output: [review_gate_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/review_gate_2026-08-02.txt)

### Commands Run (reproducible)

```bash
python -m pytest -q tests/features/
python scripts/run_study_batch.py
python scripts/repro_invented_topics.py
python scripts/repro_review_gate.py
```

### Pass/Fail Summary

- Grounding allow-list + invented-topic blocking: PASS
- Human-review gate enforced: PASS
- Batch evaluation metrics emitted and stable: PASS

### Bug Filings (with repro steps)

- Full list: [bugs_2026-08-02.md](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/bugs_2026-08-02.md)
- BUG-001 (Fixed): `scripts/repro_review_gate.py` fails when executed directly
  - Repro:
    - `python scripts/repro_review_gate.py`
  - Expected:
    - Script runs end-to-end and raises `ExportBlockedError` until approval.
  - Actual (before fix):
    - `ModuleNotFoundError: No module named 'src'`
  - Evidence:
    - [review_gate_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/review_gate_2026-08-02.txt)
- BUG-002 (Fixed): Flashcard count metric always passes
  - Repro:
    - `python -m pytest -q tests/features/test_study_eval.py -k test_flashcard_count_mismatch_is_detected`
  - Expected:
    - Evaluation fails when `len(cards) != expected_count`.
  - Actual (before fix):
    - Metric could pass even if fewer cards were produced.
- BUG-003 (Fixed): Plan completeness metric always passes
  - Repro:
    - `python -m pytest -q tests/features/test_study_eval.py -k test_plan_completeness_requires_all_extracted_topics`
  - Expected:
    - Metric fails when not all extracted topics are scheduled.
  - Actual (before fix):
    - Metric could pass even when scheduling only a subset.
- BUG-004 (Open): Running full `pytest tests/` fails in current environment due to missing deps
  - Repro:
    - `python -m pytest -q tests/`
  - Expected:
    - Tests collect and run (or skip optional-dep tests).
  - Actual:
    - Collection fails with missing `openai` / `chromadb`.
