
from .schema import Document, Chunk
from .parser import TextParser
from .cleaner import TextCleaner
from .chunker import TextChunker
from .store import SQLiteStore


class ContentLoader:
    def __init__(self, db_path: str = "ingestion.db"):
        self.store = SQLiteStore(db_path)
        self.cleaner = TextCleaner()
        self.chunker = TextChunker()
    
    def load_file(self, file_content: bytes, filename: str, source_type: str = "file") -> Document:
        # Determine file type
        file_type = filename.split('.')[-1].lower() if '.' in filename else None
        
        # Parse file
        raw_text = TextParser.parse(file_content, file_type)
        
        # Clean text
        cleaned_text = self.cleaner.clean(raw_text)
        
        # Create document
        document = Document(
            title=filename,
            content=cleaned_text,
            source_type=source_type,
            file_type=file_type
        )
        
        # Save document
        saved_doc = self.store.add_document(document)
        
        # Create chunks
        chunks = self.chunker.chunk(saved_doc.content, saved_doc.id)
        
        # Save chunks
        self.store.add_chunks(chunks)
        
        return saved_doc
    
    def load_text(self, text: str, title: str = "Pasted Text", source_type: str = "paste") -> Document:
        # Clean text
        cleaned_text = self.cleaner.clean(text)
        
        # Create document
        document = Document(
            title=title,
            content=cleaned_text,
            source_type=source_type
        )
        
        # Save document
        saved_doc = self.store.add_document(document)
        
        # Create chunks
        chunks = self.chunker.chunk(saved_doc.content, saved_doc.id)
        
        # Save chunks
        self.store.add_chunks(chunks)
        
        return saved_doc
