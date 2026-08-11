/**
 * Export service — the seam between the review/export UI and the backend.
 *
 * Handles the human-review gate: only approved outputs are exportable, and the
 * backend enforces that itself. This service triggers the actual browser
 * download by creating a temporary object URL from the returned Blob.
 */
import * as exportApi from "@/api/export.api";
import type { ExportFormat, ExportRequest } from "@/types/api/export.contracts";

export const ExportService = {
  /**
   * Request an export (real backend when not in mock mode) and hand the file to
   * the browser as a genuine download.
   */
  async exportApproved(req: {
    workspaceId: string;
    format?: ExportFormat;
    outputId?: string;
    title?: string;
  }): Promise<void> {
    const body: ExportRequest = {
      workspaceId: req.workspaceId,
      format: req.format ?? "json",
      title: req.title ?? "Approved Study Content",
    };
    if (req.outputId) body.output_id = req.outputId;

    const { blob, filename } = await exportApi.exportContent(body);

    // Trigger a real browser download from an object URL.
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },

  /** List completed exports for a workspace (for the History page integration). */
  list: (workspaceId: string) => exportApi.listExports(workspaceId),
};
