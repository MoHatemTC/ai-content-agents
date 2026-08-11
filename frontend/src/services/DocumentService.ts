/** Document + lecture-notes business logic. */
import * as documentApi from "@/api/document.api";
import type { WsChunk, WsDoc } from "@/types/domain";

export const DocumentService = {
  async listDocuments(workspaceId: string): Promise<WsDoc[]> {
    return (await documentApi.getDocuments(workspaceId)).documents;
  },

  async listChunks(workspaceId: string, documentId: string): Promise<WsChunk[]> {
    return (await documentApi.getChunks(workspaceId, documentId)).chunks;
  },

  /** Persist a new document record (text note or staged upload). */
  async createDocument(workspaceId: string, doc: WsDoc): Promise<WsDoc> {
    return (await documentApi.createDocument({ workspaceId, doc })).document;
  },

  /** Persist edits to a document record. */
  async updateDocument(workspaceId: string, id: string, patch: Partial<WsDoc>): Promise<void> {
    await documentApi.updateDocument({ workspaceId, id, patch });
  },

  async saveNotes(workspaceId: string, documentId: string, notes: string): Promise<void> {
    await documentApi.saveDocumentNotes({ workspaceId, documentId, notes });
  },

  deleteDocument: documentApi.deleteDocument,
};
