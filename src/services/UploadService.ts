/**
 * Upload pipeline: upload (storage) → store (record) → parse → chunk → embed.
 * The first two steps are the critical path: file bytes land in the private
 * `documents` bucket and a `documents` row is created. The AI enrichment
 * stages (parse/chunk/embed via FastAPI) are best-effort — a failure there
 * must never lose the persisted upload.
 */
import * as documentApi from "@/api/document.api";
import { logger } from "@/lib/logger";
import type { WsChunk, WsDoc } from "@/types/domain";

export interface UploadResult {
  document: WsDoc;
  storagePath: string;
  chunks: number;
  embedded: number;
  /** Warning when a pipeline stage failed — the upload itself was still saved. */
  pipelineError?: string;
}

export const UploadService = {
  /** Upload the file bytes to Supabase Storage (no record created yet). */
  upload: (workspaceId: string, file: UploadFileLike) =>
    documentApi.uploadDocument({ workspaceId, file }),
  parse: documentApi.parseDocument,
  chunk: documentApi.chunkDocument,
  embed: documentApi.embedDocument,
  /** Persist the document record (no-op in mock mode; returns the stored doc). */
  store: async (workspaceId: string, document: WsDoc, storagePath?: string): Promise<WsDoc> =>
    (
      await documentApi.createDocument({
        workspaceId,
        doc: { ...document, ...(storagePath ? { storagePath } : {}) },
      })
    ).document,

  /** Runs upload + record persist, then best-effort parse/chunk/embed. */
  async ingest(
    workspaceId: string,
    file: UploadFileLike,
    onStage?: (stage: "upload" | "parse" | "chunk" | "embed" | "store") => void,
  ): Promise<UploadResult> {
    onStage?.("upload");
    const { document, storage_path } = await UploadService.upload(workspaceId, file);
    onStage?.("store");
    const stored = await UploadService.store(workspaceId, document, storage_path);

    let chunkCount = 0;
    let embedded = 0;
    let pipelineError: string | undefined;
    let chunked: { documentId: string; chunks: WsChunk[] } = {
      documentId: stored.id,
      chunks: [],
    };
    try {
      onStage?.("parse");
      await UploadService.parse(stored.id);
      onStage?.("chunk");
      chunked = await UploadService.chunk(stored.id);
      chunkCount = chunked.chunks.length;
      if (chunkCount > 0) {
        onStage?.("embed");
        const result = await UploadService.embed(stored.id);
        embedded = result.embedded;
      }
    } catch (error) {
      pipelineError = error instanceof Error ? error.message : String(error);
      logger.warn(
        "document pipeline enrichment skipped",
        error instanceof Error ? error : new Error(String(error)),
      );
    }

    return {
      document: {
        ...stored,
        chunks: chunked.chunks,
        status: chunkCount > 0 && embedded > 0 ? "Ready" : "Processing",
      },
      storagePath: storage_path,
      chunks: chunkCount,
      embedded,
      pipelineError,
    };
  },
};

export type UploadFileLike = File | { name: string; size?: number; type?: string };
