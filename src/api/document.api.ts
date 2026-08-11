/** Document + upload pipeline endpoints (upload → parse → chunk → embed → store). */
import { delay, http } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import type { WsChunk, WsDoc } from "@/types/domain";
import type {
  ChunkDocumentResponse,
  CreateDocumentRequest,
  CreateDocumentResponse,
  EmbedDocumentResponse,
  GetChunksResponse,
  GetDocumentsResponse,
  ParseDocumentResponse,
  SaveDocumentNotesRequest,
  UpdateDocumentRequest,
  UploadDocumentRequest,
  UploadDocumentResponse,
} from "@/types/api/document.contracts";

function kindFromName(name: string): WsDoc["kind"] {
  const ext = name.split(".").pop()?.toUpperCase() ?? "";
  if (ext === "PDF" || ext === "DOCX" || ext === "PPTX" || ext === "TXT") return ext;
  return "Note";
}

function humanSize(bytes?: number): string {
  if (!bytes) return "—";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Upload the raw file bytes to the backend **for real** via ``POST /upload``.
 *
 * In real mode the file is stored by FastAPI (which owns the workspace's
 * documents), so the returned record is the FastAPI document id — that same id
 * is then used for parse → chunk → embed → search → generate. This replaces the
 * old Supabase-storage path so the whole pipeline runs against ONE backend.
 *
 * Mock mode keeps returning a local fake record so the UI still works without a
 * server.
 */
export async function uploadDocument({
  workspaceId,
  file,
}: UploadDocumentRequest): Promise<UploadDocumentResponse> {
  if (isMockMode()) {
    await delay(200);
    const id = `doc-${Date.now().toString(36)}`;
    const path = `${workspaceId}/${id}/${file.name}`;
    const document: WsDoc = {
      id,
      title: file.name.replace(/\.[^.]+$/, ""),
      kind: kindFromName(file.name),
      size: humanSize("size" in file ? file.size : undefined),
      sizeBytes: "size" in file ? file.size : undefined,
      pages: 1,
      uploaded: new Date().toISOString().slice(0, 10),
      status: "Ready",
      tags: [],
      chunks: [],
      storagePath: path,
    };
    return { document, storage_path: path };
  }
  if (!(file instanceof File)) throw new Error("Only real files can be uploaded.");
  const form = new FormData();
  form.append("workspace_id", workspaceId);
  form.append("file", file, file.name);
  // POST /upload returns { document: WsDoc, storage_path } via the shared
  // http client (auth header included automatically).
  const { document, storage_path } = await http.post<UploadDocumentResponse>(
    paths.documents.upload,
    form,
  );
  return { document: { ...document, status: "Processing" }, storage_path };
}

/**
 * Persist a document record (text notes OR a staged upload).
 *
 * In real mode the document record is created by ``POST /upload`` on the backend,
 * so this is a no-op that returns the document unchanged (the backend owns the
 * record). In mock mode it is also a pass-through.
 */
export async function createDocument({
  workspaceId,
  doc,
}: CreateDocumentRequest): Promise<CreateDocumentResponse> {
  if (isMockMode()) {
    await delay(60);
    return { document: doc };
  }
  return { document: doc };
}

/** Persist edits to a document record (title, notes, tags, size, pages). */
export async function updateDocument({ id, patch }: UpdateDocumentRequest): Promise<void> {
  if (isMockMode()) {
    await delay(50);
    return;
  }
  await http.patch<void>(paths.documents.detail(id), {
    title: patch.title,
    notes: patch.notes ?? null,
    tags: patch.tags,
    pages: patch.pages,
    sizeBytes: patch.sizeBytes,
  });
}

export async function parseDocument(documentId: string): Promise<ParseDocumentResponse> {
  if (!isMockMode()) return http.post<ParseDocumentResponse>(paths.documents.parse(documentId));
  await delay(120);
  return { documentId, pages: 1, text_length: 0 };
}

export async function chunkDocument(documentId: string): Promise<ChunkDocumentResponse> {
  if (!isMockMode()) return http.post<ChunkDocumentResponse>(paths.documents.chunk(documentId));
  await delay(120);
  const chunks: WsChunk[] = [];
  return { documentId, chunks };
}

export async function embedDocument(documentId: string): Promise<EmbedDocumentResponse> {
  if (!isMockMode()) return http.post<EmbedDocumentResponse>(paths.documents.embed(documentId));
  await delay(120);
  return { documentId, embedded: 0, model: "mock-embed-001" };
}

/** Load the documents belonging to one workspace (newest first). */
export async function getDocuments(workspaceId: string): Promise<GetDocumentsResponse> {
  if (isMockMode()) {
    const { getWorkspaceData } = await import("./workspace.api");
    const data = await getWorkspaceData(workspaceId);
    return { documents: data.docs };
  }
  return http.get<GetDocumentsResponse>(`${paths.documents.list}?workspace_id=${workspaceId}`);
}

/** Load documents across several workspaces in one query, grouped by workspace id. */
export async function getDocumentsForWorkspaces(
  workspaceIds: string[],
): Promise<Record<string, WsDoc[]>> {
  if (workspaceIds.length === 0) return {};
  if (isMockMode()) {
    const { getWorkspaceData } = await import("./workspace.api");
    const grouped: Record<string, WsDoc[]> = {};
    for (const id of workspaceIds) {
      const data = await getWorkspaceData(id);
      grouped[id] = data.docs;
    }
    return grouped;
  }
  const grouped: Record<string, WsDoc[]> = {};
  for (const id of workspaceIds) {
    const { documents } = await getDocuments(id);
    if (documents.length) grouped[id] = documents;
  }
  return grouped;
}

export async function getChunks(
  workspaceId: string,
  documentId: string,
): Promise<GetChunksResponse> {
  if (!isMockMode()) return http.get<GetChunksResponse>(paths.documents.chunks(documentId));
  const { documents } = await getDocuments(workspaceId);
  return { chunks: documents.find((d) => d.id === documentId)?.chunks ?? [] };
}

export async function saveDocumentNotes({
  documentId,
  notes,
}: SaveDocumentNotesRequest): Promise<void> {
  if (!isMockMode()) {
    await http.patch<void>(paths.documents.notes(documentId), { notes });
    return;
  }
  await delay(60);
}

/** Remove the document record, its chunks and its retrieval index rows. */
export async function deleteDocument(documentId: string): Promise<void> {
  if (isMockMode()) {
    await delay(60);
    return;
  }
  await http.delete<void>(paths.documents.detail(documentId));
}
