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
