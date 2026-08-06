"""
Demo educational dataset loader.

This module provides a small collection of educational documents that
can be loaded into the ingestion database for demonstrations, testing,
and development.
"""

from __future__ import annotations

from .loader import ContentLoader


class DemoDataLoader:
    """
    Loads a predefined set of educational documents into the
    ingestion database.

    The demo dataset is intended for testing the ingestion
    pipeline and populating the content library with sample
    documents.
    """

    DEMO_DOCUMENTS = [
        (
            "Introduction to Python",
            """
            Python is a high-level programming language that is widely
            used for software development, data analysis, automation,
            and artificial intelligence.

            Variables store values.

            Functions group reusable logic.

            Loops allow repeated execution of code.

            Python emphasizes readability and simplicity.
            """,
        ),
        (
            "Database Fundamentals",
            """
            A database is an organized collection of information.

            Relational databases use tables to store data.

            SQL is the standard language for querying databases.

            Primary keys uniquely identify records.

            Foreign keys establish relationships between tables.
            """,
        ),
        (
            "Computer Networks",
            """
            Computer networks enable communication between devices.

            The Internet is the world's largest computer network.

            TCP provides reliable communication.

            IP is responsible for addressing and routing packets.

            Routers forward packets between networks.
            """,
        ),
        (
            "Operating Systems",
            """
            An operating system manages computer hardware and software.

            It schedules processes.

            It manages memory.

            It controls file systems.

            It provides an interface between users and hardware.
            """,
        ),
        (
            "Object-Oriented Programming",
            """
            Object-oriented programming organizes software into objects.

            Classes define object templates.

            Objects contain data and behavior.

            Encapsulation improves maintainability.

            Inheritance and polymorphism encourage code reuse.
            """,
        ),
    ]

    def __init__(self, db_path: str = "ingestion.db") -> None:
        """
        Initialize the demo data loader.

        Args:
            db_path:
                Path to the SQLite database.
        """
        self.loader = ContentLoader(db_path)

    def load_demo_data(self) -> int:
        """
        Load the demo educational dataset into the database.

        Duplicate documents are automatically ignored by the
        ingestion pipeline's deduplication mechanism.

        Returns:
            The number of demo documents processed.
        """
        count = 0

        for title, content in self.DEMO_DOCUMENTS:
            self.loader.load_text(
                text=content,
                title=title,
                source_type="demo",
            )
            count += 1

        return count
