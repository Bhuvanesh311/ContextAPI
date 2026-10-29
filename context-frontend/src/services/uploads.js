import {
  API_BASE_URL,
  getAccessToken,
  refreshAfterUnauthorized,
} from "./api";

// Backend limits (app/knowledge/uploads/constants.py).
export const UPLOAD_LIMITS = {
  maxFiles: 10,
  maxBytes: 500 * 1024 * 1024,
  extensions: new Set(
    (
      "pdf docx doc txt md rst rtf odt ods odp pptx ppt xlsx xls csv tsv json yaml yml xml html htm " +
      "ini conf cfg properties toml log sql py js ts jsx tsx java go cs php c cpp cc cxx h hpp hh rs rb " +
      "swift kt kts scala sh bash lua r dart vb png jpg jpeg bmp tif tiff webp zip tar tgz gz"
    ).split(" "),
  ),
};

// For <input type="file" accept>.
export const UPLOAD_ACCEPT = [...UPLOAD_LIMITS.extensions]
  .map((ext) => `.${ext}`)
  .join(",");

// Why the backend would refuse this file, or null when it is fine to send.
export function uploadProblem(file) {
  const dot = file.name.lastIndexOf(".");
  const ext = dot > 0 ? file.name.slice(dot + 1).toLowerCase() : "";

  if (!UPLOAD_LIMITS.extensions.has(ext)) {
    return `${file.name}: ${ext ? `.${ext}` : "files without an extension"} not supported`;
  }
  if (ext === "gz" && !/\.tar\.gz$/i.test(file.name)) {
    return `${file.name}: only .tar.gz archives are supported`;
  }
  if (file.size === 0) return `${file.name}: the file is empty`;
  if (file.size > UPLOAD_LIMITS.maxBytes) return `${file.name}: larger than 500 MB`;

  return null;
}

function errorFromBody(body, status) {
  const detail = body?.detail ?? body?.message;

  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? String(item)).join("; ");
  if (typeof detail?.message === "string") return detail.message;
  if (status === 0) return "Cannot reach the server. Is the backend running?";

  return `Upload failed (${status})`;
}

// One POST /upload/ (at most UPLOAD_LIMITS.maxFiles files). Uses XHR because
// fetch cannot report upload progress, which matters for large files.
function uploadBatch(projectId, files, onProgress, retried = false) {
  const form = new FormData();
  form.append("project_id", projectId);
  files.forEach((file) => form.append("files", file, file.name));

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/upload/`);

    const token = getAccessToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (event) => onProgress?.(event.loaded);
    xhr.onerror = () => reject(new Error(errorFromBody(null, 0)));
    xhr.onload = async () => {
      let body = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }

      if (xhr.status === 401 && !retried) {
        try {
          await refreshAfterUnauthorized();
          uploadBatch(projectId, files, onProgress, true).then(resolve, reject);
        } catch (error) {
          reject(error);
        }
        return;
      }

      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(errorFromBody(body, xhr.status)));
        return;
      }

      resolve(body);
    };

    xhr.send(form);
  });
}

/**
 * Uploads any number of files: checks each against the backend limits, then
 * sends them in batches of UPLOAD_LIMITS.maxFiles, reporting bytes sent overall
 * as onProgress({ sent, total }).
 *
 * Returns { uploaded: File[], skipped: string[], error?: string }; files after
 * a failed batch are not sent.
 */
export async function uploadFiles(projectId, files, onProgress) {
  const skipped = [];
  const ok = [];

  for (const file of files) {
    const problem = uploadProblem(file);
    if (problem) skipped.push(problem);
    else ok.push(file);
  }

  const total = ok.reduce((sum, file) => sum + file.size, 0);
  const uploaded = [];
  let done = 0;

  for (let i = 0; i < ok.length; i += UPLOAD_LIMITS.maxFiles) {
    const batch = ok.slice(i, i + UPLOAD_LIMITS.maxFiles);

    try {
      await uploadBatch(projectId, batch, (sent) =>
        onProgress?.({ sent: done + sent, total }),
      );
    } catch (error) {
      return { uploaded, skipped, error: error.message || "Upload failed." };
    }

    done += batch.reduce((sum, file) => sum + file.size, 0);
    uploaded.push(...batch);
    onProgress?.({ sent: done, total });
  }

  return { uploaded, skipped };
}

// One line for the user about skipped files and a failed batch, or "".
export function describeUploadOutcome(outcome) {
  const parts = [];

  if (outcome.error) parts.push(outcome.error);
  if (outcome.skipped.length) {
    parts.push(
      `Skipped ${outcome.skipped.length} file${outcome.skipped.length > 1 ? "s" : ""}: ${outcome.skipped.join("; ")}.`,
    );
  }

  return parts.join(" ");
}

export function uploadPercent(progress) {
  if (!progress?.total) return 0;
  return Math.min(100, Math.round((progress.sent / progress.total) * 100));
}
