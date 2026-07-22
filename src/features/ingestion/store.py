
from typing import List, Optional
import uuid
import sqlite3
from datetime import datetime
from .schema import Document, Chunk
from .dedupe import Deduplicator


class SQLiteStore:
    def __init__(self, db_path: str = "ingestion.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source_type TEXT NOT NULL,
                file_type TEXT,
                created_at TEXT NOT NULL,
                content_hash TEXT UNIQUE NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                content TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                start_char INTEGER,
                end_char INTEGER,
                FOREIGN KEY (document_id) REFERENCES documents (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_document(self, document: Document) -> Document:
        content_hash = Deduplicator.compute_hash(document.content)
        existing_doc = self.get_document_by_hash(content_hash)
        if existing_doc:
            return existing_doc
        
        document.id = str(uuid.uuid4())
        document.content_hash = content_hash
        document.created_at = datetime.now()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO documents (id, title, content, source_type, file_type, created_at, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            document.id,
            document.title,
            document.content,
            document.source_type,
            document.file_type,
            document.created_at.isoformat(),
            document.content_hash
        ))
        
        conn.commit()
        conn.close()
        return document
    
    def get_document_by_hash(self, content_hash: str) -> Optional[Document]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM documents WHERE content_hash = ?', (content_hash,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Document(
                id=row[0],
                title=row[1],
                content=row[2],
                source_type=row[3],
                file_type=row[4],
                created_at=datetime.fromisoformat(row[5]),
                content_hash=row[6]
            )
        return None
    
    def add_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for chunk in chunks:
            chunk.id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO chunks (id, document_id, content, chunk_index, start_char, end_char)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                chunk.id,
                chunk.document_id,
                chunk.content,
                chunk.chunk_index,
                chunk.start_char,
                chunk.end_char
            ))
        
        conn.commit()
        conn.close()
        return chunks
    
    def get_chunks_by_document_id(self, document_id: str) -> List[Chunk]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM chunks WHERE document_id = ?', (document_id,))
        rows = cursor.fetchall()
        conn.close()
        
        chunks = []
        for row in rows:
            chunks.append(Chunk(
                id=row[0],
                document_id=row[1],
                content=row[2],
                chunk_index=row[3],
                start_char=row[4],
                end_char=row[5]
            ))
        return chunks
