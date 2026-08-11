import type { WsChunk, WsDoc } from "@/types/domain";

export interface UploadDocumentRequest {
  workspaceId: string;
  file: File | { name: string; size?: number; type?: string };
}

export interface UploadDocumentResponse {
  document: WsDoc;
  storage_path: string;
}

export interface CreateDocumentRequest {
  workspaceId: string;
  doc: WsDoc;
}

export interface CreateDocumentResponse {
  document: WsDoc;
}

export interface UpdateDocumentRequest {
  workspaceId: string;
  id: string;
  patch: Partial<WsDoc>;
}

export interface ParseDocumentResponse {
  documentId: string;
  pages: number;
  text_length: number;
}

export interface ChunkDocumentResponse {
  documentId: string;
  chunks: WsChunk[];
}

export interface EmbedDocumentResponse {
  documentId: string;
  embedded: number;
  model: string;
}

export interface GetDocumentsResponse {
  documents: WsDoc[];
}

export interface GetChunksResponse {
  chunks: WsChunk[];
}

export interface SaveDocumentNotesRequest {
  workspaceId: string;
  documentId: string;
  notes: string;
}
