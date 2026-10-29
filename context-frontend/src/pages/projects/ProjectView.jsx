import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Pencil, X } from "lucide-react";
import { apiFetch } from "../../services/api";
import {
  isProcessing,
  statusLabel,
  stopDocument,
} from "../../services/documents";
import {
  describeUploadOutcome,
  UPLOAD_ACCEPT,
  uploadFiles,
  uploadPercent,
} from "../../services/uploads";
import "./ProjectView.css";

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
}

function formatSize(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function getErrorMessage(data, fallback) {
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) {
    return data.detail.map((item) => item.msg).join(", ");
  }
  return data?.message || fallback;
}

const CHART_COLORS = [
  "#b86e36",
  "#d6a16f",
  "#76513b",
  "#e1c2a2",
  "#8d765e",
  "#c18a56",
  "#a84f32",
  "#9b9a76",
];

export default function ProjectView() {
  const { projectId } = useParams();
  const navigate = useNavigate();

  const [project, setProject] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [error, setError] = useState("");
  const [documentError, setDocumentError] = useState("");
  const [notice, setNotice] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [search, setSearch] = useState("");
  const [documentPage, setDocumentPage] = useState(1);
  const documentsPerPage = 10;

  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");
  const [editForm, setEditForm] = useState({
    name: "",
    description: "",
    status: "pending",
  });
  const [projectEditMode, setProjectEditMode] = useState(false);

  const loadProject = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response = await apiFetch(
        `/projects/${encodeURIComponent(projectId)}`,
      );
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(getErrorMessage(data, "Unable to load project."));
      }

      setProject(data);
      setEditForm({
        name: data.name || "",
        description: data.description || "",
        status: String(data.status || "pending").toLowerCase(),
      });
    } catch (err) {
      setError(err.message || "Unable to load project.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  // `silent` refreshes in the background (status polling) without the loader.
  const loadDocuments = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setDocumentsLoading(true);
      setDocumentError("");
    }

    try {
      const params = new URLSearchParams({
        project_id: projectId,
        page: "1",
        page_size: "100",
        sort_by: "created_at",
        order: "desc",
      });

      const response = await apiFetch(`/upload/documents?${params}`);
      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          getErrorMessage(result, "Unable to load project documents."),
        );
      }

      const payload = result.data ?? result;
      setDocuments(Array.isArray(payload.documents) ? payload.documents : []);
    } catch (err) {
      if (!silent) setDocumentError(err.message || "Unable to load documents.");
    } finally {
      if (!silent) setDocumentsLoading(false);
    }
  }, [projectId]);

  // Follow processing documents until they finish (or are stopped).
  const anyProcessing = documents.some(isProcessing);
  useEffect(() => {
    if (!anyProcessing) return undefined;
    const timer = window.setInterval(
      () => loadDocuments({ silent: true }),
      3000,
    );
    return () => window.clearInterval(timer);
  }, [anyProcessing, loadDocuments]);

  useEffect(() => {
    loadProject();
    loadDocuments();
  }, [loadProject, loadDocuments]);

  const documentStats = useMemo(() => {
    const groups = {};

    for (const document of documents) {
      const extension = String(
        document.extension ||
          document.original_filename?.split(".").pop() ||
          "unknown",
      )
        .replace(/^\./, "")
        .toUpperCase();

      groups[extension] = (groups[extension] || 0) + 1;
    }

    const entries = Object.entries(groups).sort((a, b) => b[1] - a[1]);
    const total = documents.length;

    let cumulative = 0;
    const segments = entries.map(([extension, count], index) => {
      const start = cumulative;
      cumulative += total ? (count / total) * 100 : 0;

      return {
        extension,
        count,
        percentage: total ? (count / total) * 100 : 0,
        start,
        end: cumulative,
        color: CHART_COLORS[index % CHART_COLORS.length],
      };
    });

    const gradient = segments.length
      ? `conic-gradient(${segments
          .map(
            (segment) => `${segment.color} ${segment.start}% ${segment.end}%`,
          )
          .join(", ")})`
      : "conic-gradient(#b7a18d 0% 100%)";

    return { entries: segments, total, gradient };
  }, [documents]);

  const filteredDocuments = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return documents;

    return documents.filter((document) =>
      String(document.original_filename || document.name || "")
        .toLowerCase()
        .includes(query),
    );
  }, [documents, search]);

  const totalDocumentPages = Math.ceil(
    filteredDocuments.length / documentsPerPage,
  );

  const paginatedDocuments = useMemo(() => {
    const startIndex = (documentPage - 1) * documentsPerPage;
    return filteredDocuments.slice(startIndex, startIndex + documentsPerPage);
  }, [filteredDocuments, documentPage]);

  useEffect(() => {
    const maxPage = Math.max(1, totalDocumentPages);
    if (documentPage > maxPage) {
      setDocumentPage(maxPage);
    }
  }, [documentPage, totalDocumentPages]);

  async function handleUpload(event) {
    event.preventDefault();

    setNotice("");
    setDocumentError("");

    if (!selectedFiles.length) {
      setDocumentError("Choose at least one file to upload.");
      return;
    }

    setUploading(true);
    setUploadProgress(null);

    try {
      // Validates each file and sends them in batches of 10 (the API limit).
      const outcome = await uploadFiles(
        projectId,
        selectedFiles,
        setUploadProgress,
      );
      const problem = describeUploadOutcome(outcome);

      if (outcome.uploaded.length) {
        setNotice(`Upload submitted successfully (${outcome.uploaded.length} file(s)).`);
      }

      // Keep the files that were not sent so they can be retried.
      const sent = new Set(outcome.uploaded);
      setSelectedFiles((current) => current.filter((file) => !sent.has(file)));

      if (problem) {
        setDocumentError(problem);
      } else {
        const input = document.getElementById("project-document-files");
        if (input) input.value = "";
      }

      if (outcome.uploaded.length) await loadDocuments();
    } catch (err) {
      setDocumentError(err.message || "Unable to upload documents.");
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  }

  async function handleSaveProject(event) {
    event.preventDefault();
    setEditError("");
    setNotice("");

    const trimmedName = editForm.name.trim();
    const trimmedDescription = editForm.description.trim();

    if (trimmedName.length < 3 || trimmedName.length > 100) {
      setEditError("Project name must be between 3 and 100 characters.");
      return;
    }

    if (trimmedDescription.length > 1000) {
      setEditError("Description cannot exceed 1,000 characters.");
      return;
    }

    setSaving(true);

    try {
      const response = await apiFetch(
        `/projects/${encodeURIComponent(projectId)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: trimmedName,
            description: trimmedDescription || null,
            status: editForm.status,
          }),
        },
      );

      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(getErrorMessage(result, "Unable to update project."));
      }

      const updatedProject = result.project ?? result.data?.project ?? result;
      setProject(updatedProject);
      setEditForm({
        name: updatedProject.name || trimmedName,
        description: updatedProject.description || "",
        status: String(updatedProject.status || editForm.status).toLowerCase(),
      });
      setEditOpen(false);
      setNotice(result.message || "Project updated successfully.");
    } catch (err) {
      setEditError(err.message || "Unable to update project.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRenameDocument(document) {
    const currentName = document.original_filename || document.name || "";
    const newName = window.prompt("Enter the new document name:", currentName);

    if (newName === null || !newName.trim() || newName.trim() === currentName) {
      return;
    }

    setDocumentError("");
    setNotice("");

    try {
      const response = await apiFetch(
        `/upload/documents/${encodeURIComponent(document.document_id)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ original_filename: newName.trim() }),
        },
      );

      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(getErrorMessage(result, "Unable to rename document."));
      }

      setNotice(result.message || "Document renamed successfully.");
      await loadDocuments();
    } catch (err) {
      setDocumentError(err.message || "Unable to rename document.");
    }
  }

  async function handleStopDocument(document) {
    const id = document.document_id;
    const previous = document;

    setDocumentError("");
    setNotice("");
    // Show it stopped at once; the request kills the work in the background.
    setDocuments((current) =>
      current.map((item) =>
        item.document_id === id
          ? { ...item, indexing_status: "CANCELLED", status_reason: "Stopped by user." }
          : item,
      ),
    );

    try {
      await stopDocument(id);
      setNotice(`Stopped processing "${document.original_filename}".`);
    } catch (err) {
      if (err.status === 409) {
        // It finished in the meantime: show its real status.
        await loadDocuments({ silent: true });
        return;
      }
      setDocuments((current) =>
        current.map((item) => (item.document_id === id ? previous : item)),
      );
      setDocumentError(err.message);
    }
  }

  async function handleDeleteDocument(document) {
    const name = document.original_filename || document.name || "this document";

    if (!window.confirm(`Delete "${name}"? This cannot be undone.`)) return;

    setDocumentError("");
    setNotice("");

    try {
      const response = await apiFetch(
        `/upload/documents/${encodeURIComponent(document.document_id)}`,
        { method: "DELETE" },
      );

      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(getErrorMessage(result, "Unable to delete document."));
      }

      setNotice("Document deleted successfully.");
      await loadDocuments();
    } catch (err) {
      setDocumentError(err.message || "Unable to delete document.");
    }
  }

  if (loading) {
    return (
      <main className="infer-project-view">
        <div className="project-view-state">
          <div className="project-view-loader" />
          <h2>Loading project</h2>
          <p>Fetching your project details…</p>
        </div>
      </main>
    );
  }

  if (error || !project) {
    return (
      <main className="infer-project-view">
        <Link className="project-view-back" to="/projects">
          ← Back to projects
        </Link>
        <div className="project-view-state">
          <h2>Unable to open project</h2>
          <p>{error || "Project not found."}</p>
          <button className="project-view-primary" onClick={loadProject}>
            Try again
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="infer-project-view">
      <nav className="project-view-breadcrumb">
        <button
          type="button"
          className="project-back-button"
          onClick={() => navigate(-1)}
          aria-label="Go back to previous page"
          title="Go back"
        >
          <ArrowLeft size={20} />
        </button>

        <span className="project-view-eyebrow">Projects</span>
      </nav>

      <section className="project-view-hero">
        <div className="project-view-hero-content">
          <span className="project-view-eyebrow">
            <span className="project-view-dot" />
            PROJECT WORKSPACE
          </span>

          <h1>{project.name}</h1>
          <p className="project-view-description">
            {project.description ||
              "No project description has been added yet."}
          </p>

          <div className="project-view-meta">
            {/* <span>
              Project ID: <strong>{project.project_id}</strong>
            </span> */}
            <span
              className={`project-view-status status-${String(project.status).toLowerCase()}`}
            >
              <span className="project-view-dot" />
              {project.status}
            </span>
          </div>
        </div>

        <button
          className="project-view-primary"
          type="button"
          onClick={() => {
            setEditError("");
            setEditForm({
              name: project.name || "",
              description: project.description || "",
              status: String(project.status || "pending").toLowerCase(),
            });
            setEditOpen((open) => !open);
          }}
        >
          ✎ {editOpen ? "Close editor" : "Edit Project"}
        </button>
      </section>

      {notice && (
        <div className="project-view-notice" role="status">
          {notice}
        </div>
      )}

      {editOpen && (
        <section className="project-view-panel project-edit-panel">
          <div className="project-view-section-heading project-edit-heading">
            <div>
              <span className="project-view-eyebrow">PROJECT SETTINGS</span>
              <h2>{projectEditMode ? "Edit Project" : "Project Details"}</h2>
            </div>

            <div className="project-edit-heading-actions">
              {!projectEditMode ? (
                <button
                  type="button"
                  className="project-edit-icon-button"
                  onClick={() => {
                    setEditError("");
                    setEditForm({
                      name: project.name || "",
                      description: project.description || "",
                      status: String(project.status || "pending").toLowerCase(),
                    });
                    setProjectEditMode(true);
                  }}
                  title="Edit project"
                  aria-label="Edit project"
                >
                  <Pencil size={17} />
                </button>
              ) : (
                <button
                  type="button"
                  className="project-edit-icon-button"
                  onClick={() => {
                    setEditError("");
                    setEditForm({
                      name: project.name || "",
                      description: project.description || "",
                      status: String(project.status || "pending").toLowerCase(),
                    });
                    setProjectEditMode(false);
                  }}
                  disabled={saving}
                  title="Cancel editing"
                  aria-label="Cancel editing"
                >
                  <X size={18} />
                </button>
              )}
            </div>
          </div>

          <form className="project-edit-form" onSubmit={handleSaveProject}>
            <label htmlFor="edit-project-name">Project name *</label>
            <input
              id="edit-project-name"
              value={projectEditMode ? editForm.name : project.name || ""}
              readOnly={!projectEditMode}
              minLength={3}
              maxLength={100}
              onChange={(event) =>
                setEditForm({ ...editForm, name: event.target.value })
              }
              required
            />

            <label htmlFor="edit-project-description">Description</label>
            <textarea
              id="edit-project-description"
              value={
                projectEditMode
                  ? editForm.description
                  : project.description || ""
              }
              readOnly={!projectEditMode}
              maxLength={1000}
              rows={4}
              onChange={(event) =>
                setEditForm({ ...editForm, description: event.target.value })
              }
            />

            <label htmlFor="edit-project-status">Status</label>
            <select
              id="edit-project-status"
              value={
                projectEditMode
                  ? editForm.status
                  : String(project.status || "pending").toLowerCase()
              }
              disabled={!projectEditMode}
              onChange={(event) =>
                setEditForm({ ...editForm, status: event.target.value })
              }
            >
              <option value="pending">Pending</option>
              <option value="active">Active</option>
            </select>

            {editError && (
              <p className="project-view-error" role="alert">
                {editError}
              </p>
            )}

            {projectEditMode && (
              <div className="project-view-form-actions">
                <button
                  type="button"
                  className="project-view-secondary"
                  disabled={saving}
                  onClick={() => {
                    setEditError("");
                    setEditForm({
                      name: project.name || "",
                      description: project.description || "",
                      status: String(project.status || "pending").toLowerCase(),
                    });
                    setProjectEditMode(false);
                  }}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="project-view-primary"
                  disabled={saving}
                >
                  {saving ? "Saving…" : "Save Changes"}
                </button>
              </div>
            )}
          </form>
        </section>
      )}

      <section className="project-view-details">
        <div className="project-view-section-heading">
          <div>
            <span className="project-view-eyebrow">PROJECT INFORMATION</span>
            <h2>Overview</h2>
          </div>
        </div>

        <div className="project-view-info-grid">
          <article className="project-view-info-card">
            <span>Project</span>
            <strong>{project.name}</strong>
          </article>
          <article className="project-view-info-card">
            <span>Status</span>
            <strong className="project-view-capitalize">
              {project.status}
            </strong>
          </article>
          <article className="project-view-info-card">
            <span>Created on</span>
            <strong>{formatDate(project.created_at)}</strong>
          </article>
          <article className="project-view-info-card">
            <span>Last updated</span>
            <strong>{formatDate(project.updated_at)}</strong>
          </article>
        </div>
      </section>

      <section className="project-view-documents-layout">
        <article className="project-view-panel project-document-analytics">
          <div className="project-view-section-heading">
            <div>
              <span className="project-view-eyebrow">KNOWLEDGE ANALYTICS</span>
              <h2>Documents by type</h2>
              <p>File distribution for this project only.</p>
            </div>
            <span className="project-document-total">
              {documentsLoading ? "…" : documentStats.total} files
            </span>
          </div>

          {documentsLoading ? (
            <div className="project-document-chart-state">
              Loading document analytics…
            </div>
          ) : documentError && documents.length === 0 ? (
            <div className="project-document-chart-state">
              <p>{documentError}</p>
              <button
                className="project-view-secondary"
                onClick={loadDocuments}
              >
                Retry
              </button>
            </div>
          ) : documentStats.total === 0 ? (
            <div className="project-document-chart-state">
              <div className="project-document-empty-icon">◌</div>
              <strong>No documents yet</strong>
              <p>Upload files to see the document-type breakdown.</p>
            </div>
          ) : (
            <div className="project-document-chart-content">
              <div
                className="project-document-pie"
                style={{ background: documentStats.gradient }}
                role="img"
                aria-label={`Document types: ${documentStats.entries
                  .map((item) => `${item.extension}: ${item.count}`)
                  .join(", ")}`}
              >
                <div className="project-document-pie-center">
                  <strong>{documentStats.total}</strong>
                  <span>Documents</span>
                </div>
              </div>

              <div className="project-document-legend">
                {documentStats.entries.map((item) => (
                  <div
                    className="project-document-legend-row"
                    key={item.extension}
                  >
                    <span
                      className="project-document-legend-dot"
                      style={{ background: item.color }}
                    />
                    <span className="project-document-legend-name">
                      {item.extension}
                    </span>
                    <strong>{item.count}</strong>
                    <span className="project-document-legend-percent">
                      {item.percentage.toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </article>

        <article className="project-view-panel project-document-upload">
          <div className="project-view-section-heading">
            <div>
              <span className="project-view-eyebrow">PROJECT KNOWLEDGE</span>
              <h2>Upload documents</h2>
              <p>
                Files will be assigned to <b>{project.name}</b>.
              </p>
            </div>
          </div>

          <form onSubmit={handleUpload}>
            <label
              className="project-document-dropzone"
              htmlFor="project-document-files"
            >
              <span className="project-document-upload-icon">↑</span>
              <strong>Choose files to upload</strong>
              <span>Multiple files are supported</span>
              <input
                id="project-document-files"
                type="file"
                multiple
                accept={UPLOAD_ACCEPT}
                onChange={(event) =>
                  setSelectedFiles(Array.from(event.target.files || []))
                }
              />
            </label>

            {selectedFiles.length > 0 && (
              <div className="project-document-selected">
                {selectedFiles.length} file(s) selected
                <ul>
                  {selectedFiles.map((file, index) => (
                    <li
                      key={`${file.name}-${file.size}-${index}`}
                      className="project-document-selected-item"
                    >
                      <span>
                        {file.name} · {formatSize(file.size)}
                      </span>

                      <button
                        type="button"
                        className="project-document-remove-file"
                        onClick={() => {
                          setSelectedFiles((previous) =>
                            previous.filter(
                              (_, fileIndex) => fileIndex !== index,
                            ),
                          );
                        }}
                        aria-label={`Remove ${file.name}`}
                        title="Remove file"
                      >
                        ×
                      </button>
                    </li>
                  ))}
                  {selectedFiles.length > 4 && (
                    <li>and {selectedFiles.length - 4} more…</li>
                  )}
                </ul>
              </div>
            )}

            <button
              className="project-view-primary project-document-upload-button"
              type="submit"
              disabled={uploading || selectedFiles.length === 0}
            >
              {uploading
                ? `Uploading ${uploadPercent(uploadProgress)}%`
                : "Upload to this project"}
            </button>
          </form>
        </article>
      </section>

      <section className="project-view-panel project-document-list-panel">
        <div className="project-view-section-heading project-document-list-heading">
          <div>
            <span className="project-view-eyebrow">PROJECT FILES</span>
            <h2>Document library</h2>
            <p>Only documents assigned to this project are shown here.</p>
          </div>

          <input
            className="project-document-search"
            type="search"
            placeholder="Search documents…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setDocumentPage(1);
            }}
            aria-label="Search project documents"
          />
        </div>

        {documentError && (
          <div className="project-view-error" role="alert">
            {documentError}
          </div>
        )}

        {documentsLoading ? (
          <div className="project-document-list-state">Loading documents…</div>
        ) : filteredDocuments.length === 0 ? (
          <div className="project-document-list-state">
            {documents.length === 0
              ? "No documents have been uploaded to this project yet."
              : "No documents match your search."}
          </div>
        ) : (
          <>
            <div className="project-document-table-wrap">
              <table className="project-document-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Type</th>
                    <th>Size</th>
                    <th>Processing status</th>
                    <th>Uploaded</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedDocuments.map((document) => (
                    <tr key={document.document_id}>
                      <td>
                        <div className="project-document-name">
                          <span className="project-document-file-icon">
                            {String(document.extension || "FILE")
                              .toUpperCase()
                              .slice(0, 4)}
                          </span>
                          <span>
                            <strong>
                              {document.original_filename ||
                                document.name ||
                                "Unnamed document"}
                            </strong>
                          </span>
                        </div>
                      </td>
                      <td>
                        {String(document.extension || "unknown").toUpperCase()}
                      </td>
                      <td>{formatSize(document.size_bytes || 0)}</td>
                      <td>
                        <span className="project-document-status">
                          {statusLabel(
                            document.indexing_status ||
                              document.status ||
                              "Unknown",
                          )}
                        </span>
                      </td>
                      <td>{formatDate(document.created_at)}</td>
                      <td>
                        <div className="project-document-actions">
                          {isProcessing(document) && (
                            <button
                              type="button"
                              className="project-document-stop"
                              onClick={() => handleStopDocument(document)}
                              aria-label={`Stop processing ${document.original_filename}`}
                              title="Stop processing"
                            >
                              Stop
                            </button>
                          )}

                          <button
                            type="button"
                            onClick={() =>
                              window.alert(
                                "Document preview will be implemented later.",
                              )
                            }
                            aria-label={`View ${document.original_filename}`}
                            title="View document"
                          >
                            View
                          </button>

                          <button
                            type="button"
                            onClick={() =>
                              window.alert(
                                "Document download will be implemented later.",
                              )
                            }
                            aria-label={`Download ${document.original_filename}`}
                            title="Download document"
                          >
                            Download
                          </button>

                          <button
                            type="button"
                            onClick={() => handleRenameDocument(document)}
                            aria-label={`Rename ${document.original_filename}`}
                            title="Rename document"
                          >
                            Rename
                          </button>

                          <button
                            type="button"
                            className="project-document-delete"
                            onClick={() => handleDeleteDocument(document)}
                            aria-label={`Delete ${document.original_filename}`}
                            title="Delete document"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="project-document-pagination">
              <span>
                Showing {(documentPage - 1) * documentsPerPage + 1}–
                {Math.min(
                  documentPage * documentsPerPage,
                  filteredDocuments.length,
                )}{" "}
                of {filteredDocuments.length} documents
              </span>

              <div className="project-document-pagination-buttons">
                <button
                  type="button"
                  disabled={documentPage <= 1}
                  onClick={() =>
                    setDocumentPage((page) => Math.max(1, page - 1))
                  }
                >
                  Previous
                </button>

                <span>
                  Page {documentPage} of {Math.max(1, totalDocumentPages)}
                </span>

                <button
                  type="button"
                  disabled={documentPage >= totalDocumentPages}
                  onClick={() =>
                    setDocumentPage((page) =>
                      Math.min(Math.max(1, totalDocumentPages), page + 1),
                    )
                  }
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      <div className="project-view-bottom-actions">
        <button
          className="project-view-secondary"
          type="button"
          onClick={() => navigate("/projects")}
        >
          ← All projects
        </button>
        <button
          className="project-view-secondary"
          type="button"
          onClick={() => {
            loadProject();
            loadDocuments();
          }}
        >
          ↻ Refresh project
        </button>
      </div>
    </main>
  );
}
