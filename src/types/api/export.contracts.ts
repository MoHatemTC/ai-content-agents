/** Export contract — matches backend/exports/schemas.py (Phase 8, M8). */

export type ExportFormat = "json" | "csv" | "markdown" | "pdf";

export interface ExportRequest {
  /** Workspace the output belongs to (required to satisfy the ownership gate). */
  workspaceId?: string;
  /** A specific approved output to export (single-item export). */
  output_id?: string;
  /** Optionally export every approved output of a run. */
  run_id?: string;
  format: ExportFormat;
  title?: string;
}

export interface ExportRecord {
  id: string;
  run_id?: string | null;
  output_id?: string | null;
  format: string;
  title: string;
  created_at: string;
}

export interface GetExportsResponse {
  exports: ExportRecord[];
}

/** Result of a successful download: the Blob plus the suggested filename. */
export interface ExportDownload {
  blob: Blob;
  filename: string;
}
