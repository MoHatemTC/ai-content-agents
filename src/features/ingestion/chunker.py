
from typing import List
from .schema import Chunk


class TextChunker:
    def __init__(self, chunk_size: int = 1000, overlap: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk(self, text: str, document_id: str) -> List[Chunk]:
        chunks = []
        start = 0
        index = 0
        text_length = len(text)
        
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunk_content = text[start:end]
            chunks.append(Chunk(
                document_id=document_id,
                content=chunk_content,
                chunk_index=index,
                start_char=start,
                end_char=end
            ))
            start = end - self.overlap
            index += 1
        
        return chunks
