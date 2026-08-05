## Week 4 — Mentor & Concept Explanation Agents — E2E Testing (2026-08-03)

### Scope

- Agents:
  - [MentorAgent](file:///d:/Sprint/Sprint_Task1/ai-content-agents/src/agents/mentor_agent.py)
  - [ConceptAgent](file:///d:/Sprint/Sprint_Task1/ai-content-agents/src/agents/concept_agent.py)
- Validations:
  - Grounded references: [verify_references](file:///d:/Sprint/Sprint_Task1/ai-content-agents/src/retrieval/grounding.py#L78-L106)
  - Support-check (off-content claims): [validate_support](file:///d:/Sprint/Sprint_Task1/ai-content-agents/src/validation/support_validator.py#L104-L136)
  - Difficulty parameter propagation + depth behavior in mock-mode.

### Environment Notes

- This environment does not have `openai` or `chromadb` installed.
- Changes were made to allow mock-mode testing without these optional deps:
  - Agent modules now lazily import `openai` only when `MOCK_MODE=false`.
  - Retrieval package import no longer hard-fails when `chromadb` is missing (index exports become unavailable).

### Test Cases Covered

- Grounding + references:
  - When `context` is supplied, the agent must cite only `context.chunk_ids`.
  - Agent prompt must include `[{chunk_id}]` markers from `GroundedContext.as_prompt_content()`.
- Difficulty control:
  - Changing `difficulty` changes explanation depth (tested deterministically in mock-mode).
- Support-check:
  - When `context` is supplied, off-content claims are blocked (raises `ValueError`).
- Fabricated references:
  - If the LLM returns `references[*].segment_id` not present in grounded context, the agent blocks output (raises `ValueError`).

### Command

```bash
python -m pytest -q tests/test_week4_mentor_concept_e2e.py
```

### Result

- ✅ 12 passed
- Output (summary): `12 passed in 0.84s`

### Test File

- [test_week4_mentor_concept_e2e.py](file:///d:/Sprint/Sprint_Task1/ai-content-agents/tests/test_week4_mentor_concept_e2e.py)
