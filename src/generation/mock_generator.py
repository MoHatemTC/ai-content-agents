from typing import Dict, Any
from datetime import date, timedelta
from .base_generator import BaseGenerator
from src.registry import AgentRegistry
from src.schemas import (
    FlashcardSet,
    Flashcard,
    StudyPlan,
    TopicSchedule,
    RevisionSession,
    RevisionItem,
)


class MockGenerator(BaseGenerator):
    def __init__(self, registry: AgentRegistry):
        super().__init__(registry)

    def generate(self, agent_name: str, inputs: Dict[str, Any]) -> Any:
        if agent_name == "flashcard_generator":
            return self._generate_flashcards(inputs)
        elif agent_name == "study_plan_generator":
            return self._generate_study_plan(inputs)
        elif agent_name == "revision_plan_generator":
            return self._generate_revision(inputs)
        else:
            raise ValueError(f"Unknown agent: {agent_name}")

    def _generate_flashcards(self, inputs: Dict[str, Any]) -> FlashcardSet:
        material = inputs.get("material", "Sample study material")
        count = inputs.get("count", 5)
        return FlashcardSet(
            title="Generated Flashcards",
            description=f"Flashcards generated from: {material}",
            cards=[
                Flashcard(
                    front=f"Question {i+1} about {material}",
                    back=f"Answer {i+1} to question about {material}",
                    tags=["sample", "generated"]
                ) for i in range(count)
            ]
        )

    def _generate_study_plan(self, inputs: Dict[str, Any]) -> StudyPlan:
        goal = inputs.get("goal", "Learn sample topic")
        topics = inputs.get("topics", ["Topic 1", "Topic 2"])
        start_date = date.fromisoformat(inputs.get("start_date", str(date.today())))
        end_date = date.fromisoformat(inputs.get("end_date", str(date.today() + timedelta(days=30))))
        
        topic_schedule = []
        days_per_topic = (end_date - start_date).days // len(topics)
        for i, topic in enumerate(topics):
            topic_start = start_date + timedelta(days=i * days_per_topic)
            topic_end = start_date + timedelta(days=(i+1)*days_per_topic)
            topic_schedule.append(TopicSchedule(
                topic=topic,
                start_date=topic_start,
                end_date=topic_end,
                duration_hours=2.0,
                resources=[]
            ))
        
        return StudyPlan(
            goal=goal,
            start_date=start_date,
            end_date=end_date,
            topic_schedule=topic_schedule
        )

    def _generate_revision(self, inputs: Dict[str, Any]) -> RevisionSession:
        topics = inputs.get("topics", ["Topic A", "Topic B"])
        start_date = date.fromisoformat(inputs.get("start_date", str(date.today())))
        
        revision_items = []
        for i, topic in enumerate(topics):
            revision_items.append(RevisionItem(
                topic=topic,
                description=f"Revision item for {topic}",
                next_revision_date=start_date + timedelta(days=i+1),
                difficulty="medium"
            ))
        
        return RevisionSession(
            session_date=start_date,
            items=revision_items,
            notes="Generated revision session"
        )
