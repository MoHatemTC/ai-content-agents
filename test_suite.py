from src.registry import AgentRegistry
from src.generation import MockGenerator
from datetime import date, timedelta


def main():
    # Initialize registry and generator
    registry = AgentRegistry()
    generator = MockGenerator(registry)
    
    # List available agents
    print("Available agents:")
    for agent in registry.list_agents():
        print(f"  - {agent.name}: {agent.description}")
    
    print("\n--- Testing Flashcard Generator ---")
    flashcards = generator.generate("flashcard_generator", {
        "material": "Python Programming Fundamentals",
        "count": 3
    })
    print(f"Title: {flashcards.title}")
    for card in flashcards.cards:
        print(f"Q: {card.front}")
        print(f"A: {card.back}")
        print()
    
    print("\n--- Testing Study Plan Generator ---")
    study_plan = generator.generate("study_plan_generator", {
        "goal": "Prepare for Python Certification Exam",
        "topics": ["Data Types", "Control Flow", "Functions", "OOP"],
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=30))
    })
    print(f"Goal: {study_plan.goal}")
    for topic in study_plan.topic_schedule:
        print(f"{topic.topic}: {topic.start_date} to {topic.end_date}")
    
    print("\n--- Testing Revision Plan Generator ---")
    revision = generator.generate("revision_plan_generator", {
        "topics": ["Data Types", "Functions"],
        "start_date": str(date.today())
    })
    print(f"Revision date: {revision.session_date}")
    for item in revision.items:
        print(f"{item.topic}: next review on {item.next_revision_date} (difficulty: {item.difficulty})")


if __name__ == "__main__":
    main()
