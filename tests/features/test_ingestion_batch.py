"""
Tests for the batch ingestion service.

These tests verify that the batch ingestion service correctly processes
multiple files, reports failures for invalid files, and ingests
directories containing supported documents.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from src.ingestion.batch import BatchIngestion


def test_ingest_multiple_files():
    """
    Verify that multiple valid files are successfully ingested.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        batch = BatchIngestion(db_path)

        files = [
            ("doc1.txt", b"This is the first document. " * 5),
            ("doc2.txt", b"This is the second document. " * 5),
        ]

        result = batch.ingest_files(files)

        assert len(result.documents) == 2
        assert len(result.failed_files) == 0

    finally:
        os.unlink(db_path)


def test_ingest_invalid_file():
    """
    Verify that invalid files are reported as failed without
    interrupting the batch ingestion process.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        batch = BatchIngestion(db_path)

        files = [
            ("notes.txt", b"This is a valid document. " * 5),
            ("image.png", b"fake image"),
        ]

        result = batch.ingest_files(files)

        assert len(result.documents) == 1
        assert len(result.failed_files) == 1
        assert result.failed_files[0].filename == "image.png"

    finally:
        os.unlink(db_path)


def test_ingest_directory():
    """
    Verify that all supported files in a directory are ingested.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as db:
        db_path = db.name

    try:
        with tempfile.TemporaryDirectory() as directory:
            text1 = (
                "Artificial intelligence enables computers to learn from data, "
                "recognize patterns, and make decisions. Machine learning is one "
                "of the most widely used approaches in AI. Engineers build models, "
                "evaluate their performance, improve them using training data, "
                "and deploy them into real-world applications. Testing and "
                "validation are essential parts of the development process."
            )

            text2 = (
                "Software engineering includes requirements gathering, system "
                "design, implementation, testing, deployment, and maintenance. "
                "Good software is reliable, maintainable, and easy to understand. "
                "Developers collaborate using version control systems, perform "
                "code reviews, and continuously improve software quality through "
                "testing and documentation."
            )

            with open(
                os.path.join(directory, "doc1.txt"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(text1)

            with open(
                os.path.join(directory, "doc2.md"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(text2)

            batch = BatchIngestion(db_path)
            result = batch.ingest_directory(directory)

            assert len(result.documents) == 2
            assert len(result.failed_files) == 0

    finally:
        os.unlink(db_path)


def test_ingest_missing_directory():
    """
    Verify that ingesting a non-existent directory raises
    FileNotFoundError.
    """
    batch = BatchIngestion()

    with pytest.raises(FileNotFoundError):
        batch.ingest_directory("directory_that_does_not_exist")


def test_ignore_unsupported_files():
    """
    Verify that unsupported file types are ignored when ingesting
    a directory.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as db:
        db_path = db.name

    try:
        with tempfile.TemporaryDirectory() as directory:
            text = (
                "This document contains enough meaningful educational content "
                "to satisfy the quality checks. It discusses software design, "
                "testing strategies, documentation practices, and collaborative "
                "development workflows that are commonly used in modern software "
                "engineering projects."
            )

            with open(
                os.path.join(directory, "notes.txt"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(text)

            with open(
                os.path.join(directory, "photo.png"),
                "wb",
            ) as f:
                f.write(b"fake image data")

            batch = BatchIngestion(db_path)
            result = batch.ingest_directory(directory)

            assert len(result.documents) == 1
            assert len(result.failed_files) == 0
            assert result.documents[0].title == "notes.txt"

    finally:
        os.unlink(db_path)
