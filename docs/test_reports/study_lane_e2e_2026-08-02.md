## Study Lane E2E Verification (2026-08-02)

### Environment

- OS: Windows
- Python: 3.12.7

### Scope

- Flashcards Agent + Study Plan Agent + Revision Agent end-to-end (mock-mode)
- Grounding (topic allow-list) + invented-topic blocking
- Human-review gate (needs_human_review + export gate)
- Batch generation + quality/groundedness metrics (AI evaluation workstream)

### Commands Run (reproducible)

- Study lane tests:
  - `python -m pytest -q tests/features/`
  - Output: [pytest_features_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/pytest_features_2026-08-02.txt)
- Batch run + benchmark:
  - `python scripts/run_study_batch.py`
  - Output: [study_batch_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/study_batch_2026-08-02.txt)
- Invented-topic repro checks:
  - `python scripts/repro_invented_topics.py`
  - Output: [invented_topics_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/invented_topics_2026-08-02.txt)
- Human-review export gate repro:
  - `python scripts/repro_review_gate.py`
  - Output: [review_gate_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/review_gate_2026-08-02.txt)

### Pass/Fail Checklist

- Grounding (topics come from real extracted allow-list): PASS
  - Evidence: `BENCHMARK.*.grounded_rate == 1.0` في [study_batch_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/study_batch_2026-08-02.txt)
- Flashcards format/count honored: PASS
  - Evidence: `FLASHCARD_COUNTS [5, 5, 5]` + `FLASHCARD_FORMATS [['term-definition'], ...]`
- Learner goal honored in plans: PASS
  - Evidence: `SAMPLE_PLAN_GOAL Prepare for Python exam`
- Invented topics are flagged/blocked: PASS
  - Evidence: كل الاختبارات في [invented_topics_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/invented_topics_2026-08-02.txt) ترفع أخطاء grounding المتوقعة (PASS)
- Human-review gate enforced: PASS
  - Evidence: `MODEL_NEEDS_REVIEW True` + `ExportBlockedError` قبل الموافقة في [review_gate_2026-08-02.txt](file:///d:/Sprint/Sprint_Task1/ai-content-agents/docs/test_reports/review_gate_2026-08-02.txt)
- Batch generation + evaluation metrics work: PASS
  - Evidence: `BENCHMARK.overall == 1.0` + all per-agent metrics high

