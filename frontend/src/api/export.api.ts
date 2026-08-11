/** Export API (Phase 8, M8) — real backend file download. */
import { http } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import type {
  ExportDownload,
  ExportRequest,
  GetExportsResponse,
} from "@/types/api/export.contracts";

function mockFilename(format: ExportRequest["format"]): string {
  const ext = format === "markdown" ? "md" : format;
  return `sensei-approved.${ext}`;
}

/**
 * Export approved study content and return the file for the browser to save.
 *
 * Real mode POSTs the request to ``/exports`` and returns the download Blob +
 * filename (the backend builds the file and streams it with a
 * ``Content-Disposition`` header). Mock mode returns a small in-memory
 * Markdown blob so the UI still exercises the download path without a server.
 */
export async function exportContent(req: ExportRequest): Promise<ExportDownload> {
  if (isMockMode()) {
    await new Promise((r) => setTimeout(r, 120));
    const raw =
      req.format === "markdown"
        ? "# Approved study content\n\nExported by Sensei."
        : JSON.stringify(req, null, 2);
    return {
      blob: new Blob([raw], { type: "text/plain;charset=utf-8" }),
      filename: mockFilename(req.format),
    };
  }
  return http.download(paths.exports.create, req);
}

export async function listExports(workspaceId: string): Promise<GetExportsResponse> {
  if (!isMockMode()) {
    return http.get<GetExportsResponse>(`${paths.exports.list}?workspace_id=${workspaceId}`);
  }
  return { exports: [] };
}
