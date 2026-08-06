from datetime import date

from pydantic import BaseModel, Field


class TopicSchedule(BaseModel):
    topic: str = Field(..., description="The name of the topic to study")
    start_date: date = Field(..., description="The start date for studying this topic")
    end_date: date = Field(..., description="The end date for studying this topic")
    duration_hours: float = Field(
        ..., description="Estimated hours to spend on this topic"
    )
    resources: list[str] | None = Field(
        default_factory=list, description="Optional list of resources for this topic"
    )


class StudyPlan(BaseModel):
    goal: str = Field(..., description="The main goal of the study plan")
    start_date: date = Field(
        ..., description="The overall start date of the study plan"
    )
    end_date: date = Field(..., description="The overall end date of the study plan")
    topic_schedule: list[TopicSchedule] = Field(
        ..., description="Schedule of topics to study"
    )
