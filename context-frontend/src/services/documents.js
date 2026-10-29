import { apiFetch } from "./api";

// indexing_status values while the backend is still working on a document.
export const PROCESSING_STATUSES = ["INGESTING", "INDEXING"];

export function isProcessing(document) {
  return PROCESSING_STATUSES.includes(
    String(document?.indexing_status ?? "").toUpperCase(),
  );
}

// What to show for an indexing_status ("CANCELLED" reads "Stopped").
export function statusLabel(status) {
  const value = String(status ?? "").toUpperCase();
  if (value === "CANCELLED") return "Stopped";
  return value.replaceAll("_", " ");
}

/**
 * Stops a document's processing now (for an archive, every member still in
 * progress). Resolves to the updated document. A document that finished in
 * the meantime rejects with error.status 409.
 */
export async function stopDocument(documentId) {
  const response = await apiFetch(
    `/upload/documents/${encodeURIComponent(documentId)}/cancel`,
    { method: "POST", headers: { Accept: "application/json" } },
  );
  const result = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = result?.detail;
    const error = new Error(
      typeof detail === "string" ? detail : "Could not stop the document.",
    );
    error.status = response.status;
    throw error;
  }

  return result.data ?? result;
}
