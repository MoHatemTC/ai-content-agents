"""
Batch ingestion utilities.

This module provides functionality for ingesting multiple files or
entire directories in a single operation.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .loader import ContentLoader
from .schema import BatchResult, FailedFile


class BatchIngestion:
    """
    Handles batch ingestion of multiple files.

    This class builds on top of ``ContentLoader`` by processing
    collections of files and reporting both successful and failed
    ingestions.
    """

    # Supported file types for ingestion
    SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".md"}

    def __init__(self, db_path: str = "ingestion.db") -> None:
        """
        Initialize the batch ingestion service.

        Args:
            db_path:
                Path to the SQLite database.
        """
        self.loader = ContentLoader(db_path)

    def ingest_files(
        self,
        files: Iterable[tuple[str, bytes]],
    ) -> BatchResult:
        """
        Ingest multiple files.

        Args:
            files:
                An iterable of (filename, file_content) pairs.

        Returns:
            A BatchResult containing successfully ingested documents
            and any failed files.
        """
        result = BatchResult()

        for filename, content in files:
            try:
                document = self.loader.load_file(content, filename)
                result.documents.append(document)

            except Exception as exc:
                result.failed_files.append(
                    FailedFile(
                        filename=filename,
                        error=str(exc),
                    )
                )

        return result

    def ingest_directory(self, directory: str | Path) -> BatchResult:
        """
        Ingest all files contained in a directory.

        Args:
            directory:
                Path to the directory containing documents.

        Returns:
            A BatchResult describing the outcome of the operation.
        """
        directory = Path(directory)

        if not directory.exists():
            raise FileNotFoundError(f"Directory '{directory}' does not exist.")

        if not directory.is_dir():
            raise NotADirectoryError(f"'{directory}' is not a directory.")

        files = []

        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                files.append(
                    (
                        path.name,
                        path.read_bytes(),
                    )
                )

        return self.ingest_files(files)
