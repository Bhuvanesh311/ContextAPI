import { apiFetch } from "./api";

const RETRIEVAL_API = "/api/v1/retrieval/requests";

export class RequestError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function errorMessage(body, status) {
  const detail = body?.detail ?? body?.message;

  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? String(item)).join("; ");
  if (typeof detail?.message === "string") return detail.message;

  return `Request failed (${status})`;
}

async function send(path, options = {}) {
  let response;
  try {
    response = await apiFetch(path, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new RequestError(0, "Cannot reach the server. Is the backend running?");
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) throw new RequestError(response.status, errorMessage(body, response.status));

  return body;
}

// Short random id (the backend caps lifecycle ids at 20 characters).
export function shortId(prefix = "") {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return prefix + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

// Network drops, rate limits and server errors are worth retrying; the
// request keeps running on the server meanwhile.
export function isTransient(error) {
  if (!(error instanceof RequestError)) return error?.name !== "AbortError";
  return error.status === 0 || error.status === 429 || error.status >= 500;
}

/**
 * Starts a question. `conversationId` groups the questions of one chat so the
 * backend can use earlier turns as context for follow-ups; `idempotencyKey`
 * makes a retried POST return the same request instead of creating another.
 */
export function askQuestion({ projectId, question, profile, conversationId, idempotencyKey, topK = 5 }) {
  return send(RETRIEVAL_API, {
    method: "POST",
    body: JSON.stringify({
      instruction: question,
      project_id: projectId,
      profile,
      top_k: topK,
      lifecycle: {
        request_id: idempotencyKey,
        correlation_id: conversationId,
        idempotency_key: idempotencyKey,
      },
    }),
  });
}

/**
 * Waits up to `waitSeconds` for the answer. While it runs, the result carries
 * `stage` ("queued" | "indexing" | "searching" | "writing") and
 * `partial_answer` (the text written so far); `done` turns true at the end.
 */
export function getAnswer(requestId, waitSeconds, signal) {
  return send(
    `${RETRIEVAL_API}/${encodeURIComponent(requestId)}/answer?wait_seconds=${waitSeconds}`,
    { signal },
  );
}

export function cancelRequest(requestId) {
  return send(`${RETRIEVAL_API}/${encodeURIComponent(requestId)}/cancel`, {
    method: "POST",
  });
}
