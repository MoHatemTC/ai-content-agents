# Flashcards, Study Plan & Revision Tools

This is the Sprint 1 implementation for the Flashcards, Study Plan & Revision lane. It includes Pydantic schemas, YAML prompts, a shared agent registry, and baseline generation code.

## Project Structure
```
.
├── pyproject.toml
├── test_suite.py
└── src/
    ├── __init__.py
    ├── generation/
    │   ├── __init__.py
    │   ├── base_generator.py
    │   └── mock_generator.py
    ├── prompts/
    │   ├── flashcards_prompt.yaml
    │   ├── revision_prompt.yaml
    │   └── study_plan_prompt.yaml
    ├── registry/
    │   ├── __init__.py
    │   └── agent_registry.py
    └── schemas/
        ├── __init__.py
        ├── flashcards.py
        ├── revision.py
        └── study_plan.py
```

## Installation
Install dependencies:
```bash
pip install pydantic pyyaml
```

## Usage
Run the test suite to verify everything works:
```bash
python test_suite.py
```

## Schemas
- **FlashcardSet**: Contains Flashcard objects with front/back content and tags
- **StudyPlan**: Defines a learning goal and topic schedule with dates and durations
- **RevisionSession**: Organizes RevisionItem objects with scheduled review dates and difficulty

## Agents
The shared registry (`AgentRegistry`) manages three agents:
1. `flashcard_generator` - Generate flashcards from study materials
2. `study_plan_generator` - Create structured study plans with goals and schedules
3. `revision_plan_generator` - Build spaced repetition revision plans
