from src.agents.registry import AgentRegistry

registry = AgentRegistry(mock_mode=True)

print("Registered Agents:")
print(registry.list_agents())

mentor = registry.get_agent("mentor")
concept = registry.get_agent("concept")

print(type(mentor).__name__)
print(type(concept).__name__)
