import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { createPortal } from "react-dom";

import {
  UploadCloud,
  Search,
  FolderOpen,
  FileText,
  RefreshCw,
  Eye,
  Pencil,
  Trash2,
  ChevronDown,
  X,
  CheckCircle2,
  Clock3,
  AlertCircle,
  BrainCircuit,
  Files,
  Download,
  CheckSquare,
  Square,
} from "lucide-react";

import "./Knowledge.css";
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

// All Knowledge API calls use the shared client so expired JWTs are refreshed
// and the original request is retried automatically.
async function apiRequest(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await apiFetch(path, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });

  if (response.status === 204) return null;

  const result = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      result.detail || result.message || `Request failed (${response.status})`,
    );
  }

  return result;
}

function unwrap(result) {
  return result?.data ?? result;
}

function getProjectId(project) {
  return (
    project?.project_id ??
    project?.id ??
    project?.projectId ??
    ""
  ).toString();
}

function getProjectName(project) {
  return (
    project?.name ??
    project?.project_name ??
    project?.title ??
    getProjectId(project)
  );
}

function getDocumentId(document) {
  return document?.document_id ?? document?.id ?? "";
}

function getFilename(document) {
  return document?.original_filename ?? document?.name ?? "Untitled document";
}

function getStatus(document) {
  return String(
    document?.indexing_status ?? document?.status ?? "UNKNOWN",
  ).toUpperCase();
}

function StatusBadge({ status }) {
  const ready = ["READY", "COMPLETED", "ACTIVE", "INDEXED"].includes(status);

  const failed = ["FAILED", "REJECTED", "ERROR", "CANCELLED"].includes(status);

  const processing = [
    "INGESTING",

    "INDEXING",

    "PROCESSING",

    "PENDING",

    "QUEUED",
  ].includes(status);

  const Icon = ready
    ? CheckCircle2
    : failed
      ? AlertCircle
      : processing
        ? Clock3
        : AlertCircle;

  return (
    <span
      className={`knowledge-status ${
        ready
          ? "is-ready"
          : failed
            ? "is-failed"
            : processing
              ? "is-processing"
              : ""
      }`}
    >
      <Icon size={14} />

      {statusLabel(status)}
    </span>
  );
}

function formatBytes(bytes = 0) {
  const value = Number(bytes);

  if (!Number.isFinite(value) || value <= 0) return "—";

  if (value < 1024) return `${value} B`;

  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;

  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  if (!value) return "—";

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString("en-IN", {
        day: "2-digit",

        month: "short",

        year: "numeric",
      });
}

export default function Knowledge() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedView = searchParams.get("view");
  const isSubview = ["ALL", "READY", "PROCESSING", "FAILED"].includes(
    requestedView,
  );

  const [projects, setProjects] = useState([]);

  const [documents, setDocuments] = useState([]);
  const [allDocuments, setAllDocuments] = useState([]);
  const [viewMode, setViewMode] = useState("ALL");
  const [subviewStatusFilter, setSubviewStatusFilter] = useState("ALL");

  const [selectedProject, setSelectedProject] = useState("");

  const [projectSearch, setProjectSearch] = useState("");

  const [showProjectOptions, setShowProjectOptions] = useState(false);

  const [search, setSearch] = useState("");

  const [statusFilter, setStatusFilter] = useState("ALL");

  const [page, setPage] = useState(1);
  const documentsPerPage = 5;

  const [pagination, setPagination] = useState({
    total_records: 0,

    total_pages: 0,
  });

  const [loading, setLoading] = useState(true);

  const [projectsLoading, setProjectsLoading] = useState(true);

  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);

  const [error, setError] = useState("");

  const [notice, setNotice] = useState("");

  const [showUpload, setShowUpload] = useState(false);

  const [selectedFiles, setSelectedFiles] = useState([]);

  const [dragging, setDragging] = useState(false);

  const [selectedDocument, setSelectedDocument] = useState(null);

  const [renameDocument, setRenameDocument] = useState(null);

  const [renameValue, setRenameValue] = useState("");

  const [actionLoading, setActionLoading] = useState(false);

  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);

  const [downloadingId, setDownloadingId] = useState(null);

  function openUploadModal() {
    setProjectSearch("");

    setShowProjectOptions(false);

    setSelectedFiles([]);

    setShowUpload(true);
  }

  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);

    try {
      const result = unwrap(await apiRequest("/projects/"));

      const list = Array.isArray(result)
        ? result
        : (result?.projects ?? result?.items ?? []);

      setProjects(list);

      if (list.length && !selectedProject) {
        setSelectedProject("");

        setProjectSearch("");
      }
    } catch (err) {
      setError(`Projects could not be loaded: ${err.message}`);
    } finally {
      setProjectsLoading(false);
    }
  }, [selectedProject]);

  const loadDocuments = useCallback(
    async ({ silent = false } = {}) => {
      // Background polling refreshes data without replacing the library with a loading state.
      if (!silent) {
        setLoading(true);
        setError("");
      }

      try {
        // Load every backend page so the cards and filtered views represent the
        // full result set, not only the currently visible page.
        const baseParams = new URLSearchParams({
          page: "1",
          page_size: "100",
          sort_by: "created_at",
          order: "desc",
        });

        if (selectedProject) baseParams.set("project_id", selectedProject);
        if (search.trim()) baseParams.set("search", search.trim());

        const firstResult = unwrap(
          await apiRequest(`/upload/documents?${baseParams.toString()}`),
        );
        let all = Array.isArray(firstResult?.documents)
          ? firstResult.documents
          : [];
        const totalPages = Number(firstResult?.pagination?.total_pages ?? 1);

        for (let nextPage = 2; nextPage <= totalPages; nextPage += 1) {
          const params = new URLSearchParams(baseParams);
          params.set("page", String(nextPage));
          const result = unwrap(
            await apiRequest(`/upload/documents?${params.toString()}`),
          );
          all = all.concat(
            Array.isArray(result?.documents) ? result.documents : [],
          );
        }

        setAllDocuments(all);

        const activeStatusFilter = isSubview
          ? subviewStatusFilter
          : statusFilter;
        const matchesStatusFilter = (doc) =>
          activeStatusFilter === "ALL" || getStatus(doc) === activeStatusFilter;
        const matchesView = (doc) => {
          // The main Knowledge Center library must remain unfiltered by card navigation.
          if (!isSubview) return true;
          const status = getStatus(doc);
          if (viewMode === "READY") {
            return ["READY", "COMPLETED", "INDEXED"].includes(status);
          }
          if (viewMode === "PROCESSING") {
            return [
              "INGESTING",
              "INDEXING",
              "PROCESSING",
              "PENDING",
              "QUEUED",
            ].includes(status);
          }
          if (viewMode === "FAILED") {
            return ["FAILED", "REJECTED", "ERROR"].includes(status);
          }
          return true;
        };

        const filtered = all.filter(
          (doc) => matchesStatusFilter(doc) && matchesView(doc),
        );
        const totalPagesForView = Math.max(
          1,
          Math.ceil(filtered.length / documentsPerPage),
        );
        const safePage = Math.min(page, totalPagesForView);
        if (safePage !== page) setPage(safePage);

        setDocuments(
          filtered.slice(
            (safePage - 1) * documentsPerPage,
            safePage * documentsPerPage,
          ),
        );
        setPagination({
          total_records: filtered.length,
          total_pages: filtered.length ? totalPagesForView : 0,
        });
      } catch (err) {
        if (!silent) {
          setError(`Documents could not be loaded: ${err.message}`);
          setDocuments([]);
          setAllDocuments([]);
          setPagination({ total_records: 0, total_pages: 0 });
        }
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [
      page,
      selectedProject,
      search,
      statusFilter,
      subviewStatusFilter,
      viewMode,
      isSubview,
      documentsPerPage,
    ],
  );

  useEffect(() => {
    if (["ALL", "READY", "PROCESSING", "FAILED"].includes(requestedView)) {
      setViewMode(requestedView);
      setSubviewStatusFilter("ALL");
      setPage(1);
    } else {
      // Returning to /knowledge restores the original document library view.
      setViewMode("ALL");
    }
  }, [requestedView]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const filteredProjects = useMemo(() => {
    const query = projectSearch.trim().toLowerCase();

    if (!query) return projects;

    return projects.filter((project) => {
      const id = getProjectId(project).toLowerCase();

      const name = String(getProjectName(project)).toLowerCase();

      return id.includes(query) || name.includes(query);
    });
  }, [projects, projectSearch]);

  const stats = useMemo(() => {
    const ready = allDocuments.filter((doc) =>
      ["READY", "COMPLETED", "INDEXED"].includes(getStatus(doc)),
    ).length;
    const processing = allDocuments.filter((doc) =>
      ["INGESTING", "INDEXING", "PROCESSING", "PENDING", "QUEUED"].includes(
        getStatus(doc),
      ),
    ).length;
    const failed = allDocuments.filter((doc) =>
      ["FAILED", "REJECTED", "ERROR"].includes(getStatus(doc)),
    ).length;
    return { total: allDocuments.length, ready, processing, failed };
  }, [allDocuments]);

  function chooseProject(project) {
    const id = getProjectId(project);

    if (!id) {
      setError("Could not select this project: project ID is missing.");

      return;
    }

    setSelectedProject(id);

    setProjectSearch(`${id} — ${getProjectName(project)}`);

    setShowProjectOptions(false);

    setError("");
  }

  function addFiles(fileList) {
    const files = Array.from(fileList ?? []);

    setSelectedFiles((current) => {
      const combined = [...current];

      for (const file of files) {
        if (
          !combined.some(
            (existing) =>
              existing.name === file.name &&
              existing.size === file.size &&
              existing.lastModified === file.lastModified,
          )
        ) {
          combined.push(file);
        }
      }

      return combined;
    });
  }

  async function handleUpload(event) {
    event.preventDefault();

    setError("");

    setNotice("");

    if (!selectedProject) {
      setError("Select a project before uploading.");

      return;
    }

    if (!selectedFiles.length) {
      setError("Choose at least one file to upload.");

      return;
    }

    setUploading(true);
    setUploadProgress(null);

    try {
      // Validates each file and sends them in batches of 10 (the API limit).
      const outcome = await uploadFiles(
        selectedProject,
        selectedFiles,
        setUploadProgress,
      );
      const problem = describeUploadOutcome(outcome);

      if (outcome.uploaded.length) {
        setNotice(
          `Uploaded ${outcome.uploaded.length} file(s). Processing status will appear when the backend updates it.`,
        );
      }

      if (problem) {
        setError(`Upload: ${problem}`);
        // Keep the files that were not sent so they can be retried.
        const sent = new Set(outcome.uploaded);
        setSelectedFiles((current) => current.filter((file) => !sent.has(file)));
      } else {
        setSelectedFiles([]);
        setShowUpload(false);
      }

      if (outcome.uploaded.length) {
        setPage(1);
        await loadDocuments();
      }
    } catch (err) {
      setError(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  }

  function toggleDocumentSelection(documentId) {
    if (documentId === null || documentId === undefined || documentId === "") {
      return;
    }

    const normalizedId = String(documentId);

    setSelectedDocumentIds((current) => {
      const normalizedCurrent = current.map(String);

      return normalizedCurrent.includes(normalizedId)
        ? current.filter((id) => String(id) !== normalizedId)
        : [...current, normalizedId];
    });
  }

  function toggleSelectAll() {
    const visibleIds = documents

      .map(getDocumentId)

      .filter((id) => id !== null && id !== undefined && id !== "")

      .map(String);

    if (visibleIds.length === 0) return;

    const allVisibleSelected = visibleIds.every((id) =>
      selectedDocumentIds.map(String).includes(id),
    );

    setSelectedDocumentIds((current) => {
      const existing = current.map(String);

      if (allVisibleSelected) {
        return existing.filter((id) => !visibleIds.includes(id));
      }

      return [...new Set([...existing, ...visibleIds])];
    });
  }

  function clearDocumentSelection() {
    setSelectedDocumentIds([]);
  }

  function handlePrepareSelected() {
    if (selectedDocumentIds.length === 0) {
      setNotice("Select at least one document first.");

      return;
    }

    setNotice(
      `Demo: ${selectedDocumentIds.length} document(s) selected for processing. Backend processing will be connected later.`,
    );
  }

  async function handleDownload(doc) {
    const id = getDocumentId(doc);

    if (!id) {
      setError("Cannot download: document ID is missing.");

      return;
    }

    setDownloadingId(id);

    setError("");

    setNotice("");

    try {
      const response = await apiFetch(
        `/upload/documents/${encodeURIComponent(id)}/download`,
        { headers: { Accept: "application/octet-stream" } },
      );

      if (!response.ok) {
        const result = await response.json().catch(() => ({}));

        throw new Error(
          result.detail ||
            result.message ||
            `Download failed (${response.status}).`,
        );
      }

      const blob = await response.blob();

      const objectUrl = URL.createObjectURL(blob);

      const link = window.document.createElement("a");

      link.href = objectUrl;

      link.download = getFilename(doc);

      window.document.body.appendChild(link);

      link.click();

      link.remove();

      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (err) {
      setError(`Download failed: ${err.message}`);
    } finally {
      setDownloadingId(null);
    }
  }

  async function handleRename(event) {
    event.preventDefault();

    if (!renameDocument || !renameValue.trim()) return;

    setActionLoading(true);

    setError("");

    setNotice("");

    try {
      await apiRequest(
        `/upload/documents/${encodeURIComponent(getDocumentId(renameDocument))}`,

        {
          method: "PATCH",

          body: JSON.stringify({
            original_filename: renameValue.trim(),
          }),
        },
      );

      setRenameDocument(null);

      setNotice("Document name updated.");

      await loadDocuments();
    } catch (err) {
      setError(`Rename failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  }

  async function handleStop(document) {
    const id = getDocumentId(document);
    if (!id) return;

    setError("");
    setNotice("");

    // Show it stopped at once; the request kills the work in the background.
    const markStopped = (list) =>
      list.map((doc) =>
        String(getDocumentId(doc)) === String(id)
          ? { ...doc, indexing_status: "CANCELLED", status_reason: "Stopped by user." }
          : doc,
      );
    setDocuments(markStopped);
    setAllDocuments(markStopped);

    try {
      await stopDocument(id);
      setNotice(`Stopped processing "${getFilename(document)}".`);
    } catch (err) {
      // 409: it finished in the meantime. Either way, show the real status.
      if (err.status !== 409) setError(`Stop failed: ${err.message}`);
    }

    await loadDocuments({ silent: true });
  }

  async function handleDelete(document) {
    const id = getDocumentId(document);

    if (!id) {
      setError("This document has no document ID.");

      return;
    }

    if (
      !window.confirm(
        `Delete "${getFilename(document)}"? This cannot be undone.`,
      )
    ) {
      return;
    }

    setActionLoading(true);

    setError("");

    setNotice("");

    try {
      await apiRequest(`/upload/documents/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });

      setNotice("Document deleted.");

      setSelectedDocumentIds((current) =>
        current.filter((selectedId) => selectedId !== id),
      );

      if (selectedDocument && getDocumentId(selectedDocument) === id) {
        setSelectedDocument(null);
      }

      await loadDocuments();
    } catch (err) {
      setError(`Delete failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  }

  useEffect(() => {
    const processingStatuses = [
      "INGESTING",
      "INDEXING",
      "PROCESSING",
      "PENDING",
      "QUEUED",
    ];
    if (
      !allDocuments.some((doc) => processingStatuses.includes(getStatus(doc)))
    )
      return undefined;
    const timer = window.setInterval(
      () => loadDocuments({ silent: true }),
      5000,
    );
    return () => window.clearInterval(timer);
  }, [allDocuments, loadDocuments]);

  useEffect(() => {
    if (!selectedDocument) return;
    const fresh = allDocuments.find(
      (doc) =>
        String(getDocumentId(doc)) === String(getDocumentId(selectedDocument)),
    );
    if (fresh && getStatus(fresh) !== getStatus(selectedDocument)) {
      setSelectedDocument(fresh);
    }
  }, [allDocuments, selectedDocument]);

  useEffect(() => {
    if (!selectedDocument && !renameDocument && !showUpload) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape" && !uploading) {
        setSelectedDocument(null);
        setRenameDocument(null);
        setShowUpload(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedDocument, renameDocument, showUpload, uploading]);

  if (isSubview) {
    const pageTitles = {
      ALL: {
        title: "All Documents",
        description:
          "Browse every document across your projects, including ongoing and completed processing.",
      },
      READY: {
        title: "Processed Documents",
        description:
          "Documents that the backend reports as ready for retrieval.",
      },
      PROCESSING: {
        title: "Ongoing Processing",
        description:
          "Track documents that are still being ingested or indexed. Select a document to view its processing stages.",
      },
      FAILED: {
        title: "Failed Documents",
        description:
          "Documents that failed or were rejected, including any error details reported by the backend.",
      },
    };
    const activePage = pageTitles[requestedView];
    return (
      <main className="infer-dashboard knowledge-page">
        <div className="knowledge-content">
          <header className="knowledge-heading">
            <div>
              <div className="knowledge-eyebrow">
                <BrainCircuit size={15} /> CONTEXTAPI / KNOWLEDGE / DOCUMENTS
              </div>
              <h1>{activePage.title}</h1>
              <p>{activePage.description}</p>
            </div>
            <div className="knowledge-heading-actions">
              <button
                type="button"
                className="knowledge-button knowledge-button-quiet"
                onClick={() => setSearchParams({})}
              >
                ← Back to Knowledge Center
              </button>
              <button
                type="button"
                className="knowledge-button knowledge-button-quiet"
                onClick={loadDocuments}
                disabled={loading}
              >
                <RefreshCw size={16} /> Refresh
              </button>
            </div>
          </header>
          {error && (
            <div className="knowledge-alert knowledge-alert-error" role="alert">
              <AlertCircle size={17} />
              <span>{error}</span>
              <button
                type="button"
                onClick={() => setError("")}
                aria-label="Dismiss"
              >
                <X size={16} />
              </button>
            </div>
          )}
          <section className="knowledge-panel knowledge-subpage-panel">
            <div className="knowledge-panel-heading">
              <div>
                <h2>{activePage.title}</h2>
                <p>
                  Filter by filename, project, or backend processing status.
                </p>
              </div>
              <span className="knowledge-count">
                {pagination.total_records} records
              </span>
            </div>
            <div className="knowledge-toolbar">
              <label className="knowledge-search">
                <Search size={17} />
                <input
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setPage(1);
                  }}
                  placeholder="Search by filename..."
                />
                {search && (
                  <button
                    type="button"
                    onClick={() => setSearch("")}
                    aria-label="Clear search"
                  >
                    <X size={15} />
                  </button>
                )}
              </label>
              <div className="knowledge-filter">
                <FolderOpen size={16} />
                <select
                  aria-label="Filter by project"
                  value={selectedProject}
                  onChange={(event) => {
                    setSelectedProject(event.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">All projects</option>
                  {projects.map((project, index) => (
                    <option
                      key={getProjectId(project) || index}
                      value={getProjectId(project)}
                    >
                      {getProjectName(project)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="knowledge-filter">
                <select
                  aria-label="Filter by status"
                  value={subviewStatusFilter}
                  onChange={(event) => {
                    setSubviewStatusFilter(event.target.value);
                    setPage(1);
                  }}
                >
                  <option value="ALL">All statuses</option>
                  <option value="INGESTING">Ingesting</option>
                  <option value="INDEXING">Indexing</option>
                  <option value="READY">Ready</option>
                  <option value="FAILED">Failed</option>
                  <option value="REJECTED">Rejected</option>
                </select>
              </div>
            </div>
            <div className="knowledge-table-wrap">
              <table className="knowledge-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Project</th>
                    <th>Processing status</th>
                    <th>Uploaded</th>
                    <th className="knowledge-actions-heading">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan="5" className="knowledge-empty">
                        <RefreshCw className="knowledge-spin" size={20} />
                        Loading documents...
                      </td>
                    </tr>
                  ) : documents.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="knowledge-empty">
                        <Files size={28} />
                        <strong>No documents found</strong>
                        <span>
                          Try another filter or return to the Knowledge Center.
                        </span>
                      </td>
                    </tr>
                  ) : (
                    documents.map((doc, index) => (
                      <tr key={getDocumentId(doc) || index}>
                        <td>
                          <div className="knowledge-file-cell">
                            <div className="knowledge-file-icon">
                              <FileText size={19} />
                            </div>
                            <div className="knowledge-file-name">
                              <strong>{getFilename(doc)}</strong>
                              <span>
                                {getDocumentId(doc) ||
                                  "Document ID unavailable"}
                              </span>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className="knowledge-project-id">
                            {doc.project_id || "—"}
                          </span>
                        </td>
                        <td>
                          <StatusBadge status={getStatus(doc)} />
                        </td>
                        <td>{formatDate(doc.created_at)}</td>
                        <td>
                          <div className="knowledge-row-actions">
                            <button
                              type="button"
                              title="View processing details"
                              aria-label={`View ${getFilename(doc)} processing details`}
                              onClick={() => setSelectedDocument(doc)}
                            >
                              <Eye size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="knowledge-pagination">
              <span>
                Showing{" "}
                {pagination.total_records === 0
                  ? 0
                  : (page - 1) * documentsPerPage + 1}
                {"–"}
                {Math.min(page * documentsPerPage, pagination.total_records)}
                {" of "}
                {pagination.total_records} documents · Page {page}
                {pagination.total_pages ? ` of ${pagination.total_pages}` : ""}
              </span>
              <div>
                <button
                  type="button"
                  className="knowledge-button knowledge-button-quiet"
                  disabled={page <= 1 || loading}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="knowledge-button knowledge-button-quiet"
                  disabled={loading || page >= (pagination.total_pages || 1)}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          </section>
          {(selectedDocument || renameDocument) &&
            createPortal(
              <div
                className="knowledge-modal-backdrop"
                onMouseDown={(event) => {
                  if (event.target === event.currentTarget) {
                    setSelectedDocument(null);
                    setRenameDocument(null);
                  }
                }}
              >
                <section
                  className="knowledge-modal knowledge-detail-modal"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="knowledge-detail-title"
                >
                  <header className="knowledge-modal-heading">
                    <div>
                      <h2 id="knowledge-detail-title">
                        {renameDocument
                          ? "Rename document"
                          : "Document processing"}
                      </h2>
                      <p>{getFilename(selectedDocument || renameDocument)}</p>
                    </div>
                    <button
                      type="button"
                      className="knowledge-icon-button"
                      onClick={() => {
                        setSelectedDocument(null);
                        setRenameDocument(null);
                      }}
                      aria-label="Close details"
                    >
                      <X size={18} />
                    </button>
                  </header>
                  {selectedDocument && (
                    <>
                      <div className="knowledge-processing-box">
                        <div className="knowledge-processing-heading">
                          <div>
                            <strong>Document processing</strong>
                            <p>
                              Highlighted stage reflects the current backend
                              status.
                            </p>
                          </div>
                          <StatusBadge status={getStatus(selectedDocument)} />
                        </div>
                        {[
                          {
                            key: "UPLOADED",
                            title: "Uploaded",
                            description:
                              "The document has been uploaded successfully.",
                          },
                          {
                            key: "INGESTING",
                            title: "Ingesting",
                            description:
                              "The document is being extracted and prepared.",
                          },
                          {
                            key: "INDEXING",
                            title: "Indexing",
                            description:
                              "The document is being prepared for retrieval.",
                          },
                          {
                            key: "READY",
                            title: "Ready",
                            description:
                              "Processing is complete and the document is ready for use.",
                          },
                        ].map((stage, index) => {
                          const status = getStatus(selectedDocument);
                          const failed = [
                            "FAILED",
                            "REJECTED",
                            "ERROR",
                          ].includes(status);
                          const rank = [
                            "UPLOADED",
                            "INGESTING",
                            "INDEXING",
                            "READY",
                          ].indexOf(status);
                          const effectiveRank =
                            rank >= 0
                              ? rank
                              : ["PENDING", "QUEUED", "PROCESSING"].includes(
                                    status,
                                  )
                                ? 1
                                : -1;
                          const stageRank = index;
                          const complete =
                            !failed && effectiveRank >= stageRank;
                          const current =
                            !failed && effectiveRank === stageRank;
                          return (
                            <div
                              className={`knowledge-processing-stage ${complete ? "is-complete" : ""} ${current ? "is-current" : ""}`}
                              key={stage.key}
                            >
                              <span className="knowledge-processing-marker">
                                {complete ? (
                                  <CheckCircle2 size={16} />
                                ) : current ? (
                                  <Clock3 size={16} />
                                ) : (
                                  index + 1
                                )}
                              </span>
                              <div>
                                <strong>{stage.title}</strong>
                                <p>{stage.description}</p>
                              </div>
                            </div>
                          );
                        })}
                        {["FAILED", "REJECTED", "ERROR"].includes(
                          getStatus(selectedDocument),
                        ) && (
                          <div className="knowledge-processing-error">
                            <AlertCircle size={17} />
                            <div>
                              <strong>Processing failed</strong>
                              <p>
                                {selectedDocument.status_reason ||
                                  selectedDocument.error_message ||
                                  selectedDocument.error ||
                                  "The backend has not provided a failure reason."}
                              </p>
                            </div>
                          </div>
                        )}
                      </div>
                      <div className="knowledge-detail-list">
                        <div>
                          <span>Document ID</span>
                          <strong>
                            {getDocumentId(selectedDocument) || "—"}
                          </strong>
                        </div>
                        <div>
                          <span>Project ID</span>
                          <strong>{selectedDocument.project_id || "—"}</strong>
                        </div>
                        <div>
                          <span>Uploaded</span>
                          <strong>
                            {formatDate(selectedDocument.created_at)}
                          </strong>
                        </div>
                      </div>
                    </>
                  )}
                </section>
              </div>,
              document.body,
            )}
        </div>
      </main>
    );
  }

  return (
    <main className="infer-dashboard knowledge-page">
      <div className="knowledge-content">
        <header className="knowledge-heading">
          <div>
            <div className="knowledge-eyebrow">
              <BrainCircuit size={15} />
              CONTEXTAPI / KNOWLEDGE
            </div>

            <h1>Knowledge Center</h1>

            <p>
              Manage project documents and monitor their indexing readiness.
            </p>
          </div>

          <div className="knowledge-heading-actions">
            <button
              type="button"
              className="knowledge-button knowledge-button-quiet"
              onClick={() => {
                loadProjects();

                loadDocuments();
              }}
              disabled={loading}
            >
              <RefreshCw size={16} />
              Refresh
            </button>

            <button
              type="button"
              className="knowledge-button knowledge-button-primary"
              onClick={openUploadModal}
            >
              <UploadCloud size={17} />
              Upload documents
            </button>
          </div>
        </header>

        {error && (
          <div className="knowledge-alert knowledge-alert-error" role="alert">
            <AlertCircle size={17} />

            <span>{error}</span>

            <button
              type="button"
              onClick={() => setError("")}
              aria-label="Dismiss"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {notice && (
          <div
            className="knowledge-alert knowledge-alert-success"
            role="status"
          >
            <CheckCircle2 size={17} />

            <span>{notice}</span>

            <button
              type="button"
              onClick={() => setNotice("")}
              aria-label="Dismiss"
            >
              <X size={16} />
            </button>
          </div>
        )}

        <section className="knowledge-stats">
          <button
            type="button"
            className="knowledge-stat-card"
            onClick={() => {
              setViewMode("ALL");
              setSubviewStatusFilter("ALL");
              setPage(1);
              setSearchParams({ view: "ALL" });
            }}
          >
            <div className="knowledge-stat-icon">
              <Files size={19} />
            </div>

            <span>Total documents</span>

            <strong>{stats.total}</strong>

            <small>Current result count</small>
          </button>

          <button
            type="button"
            className="knowledge-stat-card"
            onClick={() => {
              setViewMode("READY");
              setSubviewStatusFilter("ALL");
              setPage(1);
              setSearchParams({ view: "READY" });
            }}
          >
            <div className="knowledge-stat-icon is-green">
              <CheckCircle2 size={19} />
            </div>

            <span>Search ready</span>

            <strong>{stats.ready}</strong>

            <small>Ready across current results</small>
          </button>

          <button
            type="button"
            className="knowledge-stat-card"
            onClick={() => {
              setViewMode("PROCESSING");
              setSubviewStatusFilter("ALL");
              setPage(1);
              setSearchParams({ view: "PROCESSING" });
            }}
          >
            <div className="knowledge-stat-icon is-amber">
              <Clock3 size={19} />
            </div>

            <span>Processing</span>

            <strong>{stats.processing}</strong>

            <small>Ongoing across current results</small>
          </button>

          <button
            type="button"
            className="knowledge-stat-card"
            onClick={() => {
              setViewMode("FAILED");
              setSubviewStatusFilter("ALL");
              setPage(1);
              setSearchParams({ view: "FAILED" });
            }}
          >
            <div className="knowledge-stat-icon is-red">
              <AlertCircle size={19} />
            </div>

            <span>Needs attention</span>

            <strong>{stats.failed}</strong>

            <small>Failed or rejected across current results</small>
          </button>
        </section>

        <section className="knowledge-panel">
          <div className="knowledge-panel-heading">
            <div>
              <h2>Document library</h2>

              <p>Search documents, check status and manage files.</p>
            </div>

            <span className="knowledge-count">
              {pagination.total_records ?? documents.length} records
            </span>
          </div>

          <div className="knowledge-toolbar">
            <label className="knowledge-search">
              <Search size={17} />

              <input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);

                  setPage(1);
                }}
                placeholder="Search by filename..."
              />

              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  aria-label="Clear search"
                >
                  <X size={15} />
                </button>
              )}
            </label>

            <div className="knowledge-filter">
              <FolderOpen size={16} />

              <select
                aria-label="Filter by project"
                value={selectedProject}
                onChange={(event) => {
                  const id = event.target.value;

                  setSelectedProject(id);

                  const match = projects.find(
                    (project) => getProjectId(project) === id,
                  );

                  setProjectSearch(
                    match ? `${id} — ${getProjectName(match)}` : "",
                  );

                  setPage(1);
                }}
              >
                <option value="">All projects</option>

                {projects.map((project, index) => (
                  <option
                    key={getProjectId(project) || index}
                    value={getProjectId(project)}
                  >
                    {getProjectId(project)} — {getProjectName(project)}
                  </option>
                ))}
              </select>
            </div>

            <div className="knowledge-filter">
              <select
                aria-label="Filter by status"
                value={statusFilter}
                onChange={(event) => {
                  setStatusFilter(event.target.value);

                  setPage(1);
                }}
              >
                <option value="ALL">All statuses</option>

                <option value="ACTIVE">Active</option>

                <option value="INGESTING">Ingesting</option>

                <option value="INDEXING">Indexing</option>

                <option value="READY">Ready</option>

                <option value="FAILED">Failed</option>

                <option value="REJECTED">Rejected</option>
              </select>
            </div>
          </div>

          {selectedDocumentIds.length > 0 && (
            <div className="knowledge-selection-bar">
              <div>
                <CheckSquare size={18} />

                <span>
                  <strong>{selectedDocumentIds.length}</strong> document(s)
                  selected
                </span>
              </div>

              <button
                type="button"
                className="knowledge-button knowledge-button-primary"
                onClick={handlePrepareSelected}
              >
                <BrainCircuit size={16} />
                Prepare for processing
              </button>

              <button
                type="button"
                className="knowledge-button knowledge-button-quiet"
                onClick={() =>
                  setNotice(
                    `Demo: Download selected for ${selectedDocumentIds.length} document(s). Download integration will be added later.`,
                  )
                }
              >
                <Download size={16} />
                Download selected
              </button>

              <button
                type="button"
                className="knowledge-button knowledge-button-quiet"
                onClick={clearDocumentSelection}
              >
                <X size={16} />
                Clear selection
              </button>
            </div>
          )}

          <div className="knowledge-table-wrap">
            <table className="knowledge-table">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Select all documents on this page"
                      checked={
                        documents.length > 0 &&
                        documents.every((doc) =>
                          selectedDocumentIds.includes(
                            String(getDocumentId(doc)),
                          ),
                        )
                      }
                      onChange={toggleSelectAll}
                    />
                  </th>

                  <th>Document</th>

                  <th>Project</th>

                  <th>Size</th>

                  <th>Processing status</th>

                  <th>Uploaded</th>

                  <th className="knowledge-actions-heading">Actions</th>
                </tr>
              </thead>

              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan="7" className="knowledge-empty">
                      <RefreshCw className="knowledge-spin" size={20} />
                      Loading documents...
                    </td>
                  </tr>
                ) : documents.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="knowledge-empty">
                      <Files size={28} />

                      <strong>No documents found</strong>

                      <span>Try a different search or upload a document.</span>
                    </td>
                  </tr>
                ) : (
                  documents.map((document, index) => {
                    const id = getDocumentId(document);

                    const status = getStatus(document);

                    return (
                      <tr key={id || index}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Select ${getFilename(document)}`}
                            checked={selectedDocumentIds.includes(String(id))}
                            onChange={() => toggleDocumentSelection(id)}
                          />
                        </td>

                        <td>
                          <div className="knowledge-file-cell">
                            <div className="knowledge-file-icon">
                              <FileText size={19} />
                            </div>

                            <div className="knowledge-file-name">
                              <strong>{getFilename(document)}</strong>

                              {/* <span>{id || "Document ID unavailable"}</span> */}
                            </div>
                          </div>
                        </td>

                        <td>
                          <span className="knowledge-project-name">
                            {projects.find(
                              (project) =>
                                String(project.project_id ?? project.id) ===
                                String(document.project_id),
                            )?.name ?? "—"}
                          </span>
                        </td>

                        <td>{formatBytes(document.size_bytes)}</td>

                        <td>
                          <StatusBadge status={status} />
                        </td>

                        <td>{formatDate(document.created_at)}</td>

                        <td>
                          <div className="knowledge-row-actions">
                            {isProcessing(document) && (
                              <button
                                type="button"
                                className="knowledge-stop-button"
                                title="Stop processing"
                                aria-label={`Stop processing ${getFilename(document)}`}
                                onClick={() => handleStop(document)}
                              >
                                <Square size={14} fill="currentColor" />
                              </button>
                            )}

                            <button
                              type="button"
                              title="View details"
                              aria-label={`View ${getFilename(document)}`}
                              onClick={() => setSelectedDocument(document)}
                            >
                              <Eye size={16} />
                            </button>

                            <button
                              type="button"
                              title="Download document"
                              aria-label={`Download ${getFilename(document)}`}
                              disabled={downloadingId === id}
                              onClick={() => handleDownload(document)}
                            >
                              {downloadingId === id ? (
                                <RefreshCw
                                  size={16}
                                  className="knowledge-spin"
                                />
                              ) : (
                                <Download size={16} />
                              )}
                            </button>

                            <button
                              type="button"
                              title="Rename"
                              aria-label={`Rename ${getFilename(document)}`}
                              onClick={() => {
                                setRenameDocument(document);

                                setRenameValue(getFilename(document));
                              }}
                            >
                              <Pencil size={16} />
                            </button>

                            <button
                              type="button"
                              title="Delete"
                              aria-label={`Delete ${getFilename(document)}`}
                              disabled={actionLoading}
                              onClick={() => handleDelete(document)}
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="knowledge-pagination">
            <span>
              Showing{" "}
              {pagination.total_records === 0
                ? 0
                : (page - 1) * documentsPerPage + 1}
              {"–"}
              {Math.min(page * documentsPerPage, pagination.total_records)}
              {" of "}
              {pagination.total_records} documents · Page {page}
              {pagination.total_pages ? ` of ${pagination.total_pages}` : ""}
            </span>

            <div>
              <button
                type="button"
                className="knowledge-button knowledge-button-quiet"
                disabled={page <= 1 || loading}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
              >
                Previous
              </button>

              <button
                type="button"
                className="knowledge-button knowledge-button-quiet"
                disabled={loading || page >= (pagination.total_pages || 1)}
                onClick={() => setPage((value) => value + 1)}
              >
                Next
              </button>
            </div>
          </div>
        </section>

        {showUpload && (
          <div
            className="knowledge-modal-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !uploading) {
                setShowUpload(false);
              }
            }}
          >
            <section
              className="knowledge-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="knowledge-upload-title"
            >
              <header className="knowledge-modal-heading">
                <div>
                  <h2 id="knowledge-upload-title">Upload documents</h2>

                  <p>Choose a project and select the files to upload.</p>
                </div>

                <button
                  type="button"
                  className="knowledge-icon-button"
                  onClick={() => setShowUpload(false)}
                  disabled={uploading}
                  aria-label="Close upload dialog"
                >
                  <X size={18} />
                </button>
              </header>

              <form onSubmit={handleUpload}>
                <label className="knowledge-field-label">Project *</label>

                <div className="knowledge-project-picker">
                  <div className="knowledge-project-input">
                    <Search size={16} />

                    <input
                      value={projectSearch}
                      onFocus={() => setShowProjectOptions(true)}
                      onChange={(event) => {
                        setProjectSearch(event.target.value);

                        setSelectedProject("");

                        setShowProjectOptions(true);
                      }}
                      placeholder={
                        projectsLoading
                          ? "Loading projects..."
                          : "Search project ID or name..."
                      }
                      autoComplete="off"
                    />

                    <ChevronDown size={16} />
                  </div>

                  {showProjectOptions && (
                    <div className="knowledge-project-options">
                      {filteredProjects.length ? (
                        filteredProjects.map((project, index) => {
                          const id = getProjectId(project);

                          return (
                            <button
                              type="button"
                              key={id || index}
                              onMouseDown={(event) => event.preventDefault()}
                              onClick={() => chooseProject(project)}
                            >
                              <FolderOpen size={16} />

                              <span>
                                <strong>{getProjectName(project)}</strong>

                                <small>{id}</small>
                              </span>

                              {selectedProject === id && (
                                <CheckCircle2 size={16} />
                              )}
                            </button>
                          );
                        })
                      ) : (
                        <div className="knowledge-no-projects">
                          {projectsLoading
                            ? "Loading..."
                            : "No matching projects"}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <label className="knowledge-field-label">Files *</label>

                <div
                  className={`knowledge-dropzone ${dragging ? "is-dragging" : ""}`}
                  onDragOver={(event) => {
                    event.preventDefault();

                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(event) => {
                    event.preventDefault();

                    setDragging(false);

                    addFiles(event.dataTransfer.files);
                  }}
                >
                  <UploadCloud size={31} />

                  <strong>Drag files here or browse</strong>

                  <span>
                    Choose one or more files supported by your backend.
                  </span>

                  <label className="knowledge-button knowledge-button-quiet knowledge-browse">
                    Browse files
                    <input
                      type="file"
                      multiple
                      accept={UPLOAD_ACCEPT}
                      onChange={(event) => {
                        addFiles(event.target.files);

                        event.target.value = "";
                      }}
                    />
                  </label>
                </div>

                {selectedFiles.length > 0 && (
                  <div className="knowledge-selected-files">
                    {selectedFiles.map((file, index) => (
                      <div key={`${file.name}-${file.size}-${index}`}>
                        <FileText size={16} />

                        <span>{file.name}</span>

                        <small>{formatBytes(file.size)}</small>

                        <button
                          type="button"
                          onClick={() =>
                            setSelectedFiles((current) =>
                              current.filter(
                                (_, fileIndex) => fileIndex !== index,
                              ),
                            )
                          }
                          aria-label={`Remove ${file.name}`}
                        >
                          <X size={15} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <footer className="knowledge-modal-footer">
                  <button
                    type="button"
                    className="knowledge-button knowledge-button-quiet"
                    disabled={uploading}
                    onClick={() => setShowUpload(false)}
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    className="knowledge-button knowledge-button-primary"
                    disabled={
                      uploading || !selectedProject || !selectedFiles.length
                    }
                  >
                    <UploadCloud size={16} />

                    {uploading
                      ? `Uploading ${uploadPercent(uploadProgress)}%`
                      : `Upload ${selectedFiles.length || ""} files`}
                  </button>
                </footer>
              </form>
            </section>
          </div>
        )}

        {(selectedDocument || renameDocument) &&
          createPortal(
            <div
              className="knowledge-modal-backdrop"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  setSelectedDocument(null);
                  setRenameDocument(null);
                }
              }}
            >
              <section
                className="knowledge-modal knowledge-detail-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="knowledge-detail-title"
              >
                <header className="knowledge-modal-heading">
                  <div>
                    <h2 id="knowledge-detail-title">
                      {renameDocument ? "Rename document" : "Document details"}
                    </h2>

                    <p>
                      {renameDocument
                        ? "Update the display filename."
                        : "Document metadata and current status."}
                    </p>
                  </div>

                  <button
                    type="button"
                    className="knowledge-icon-button"
                    onClick={() => {
                      setSelectedDocument(null);

                      setRenameDocument(null);
                    }}
                    aria-label="Close details"
                  >
                    <X size={18} />
                  </button>
                </header>

                {renameDocument ? (
                  <form onSubmit={handleRename}>
                    <label
                      className="knowledge-field-label"
                      htmlFor="knowledge-rename"
                    >
                      Filename
                    </label>

                    <input
                      id="knowledge-rename"
                      className="knowledge-text-input"
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                      maxLength={255}
                      required
                      autoFocus
                    />

                    <footer className="knowledge-modal-footer">
                      <button
                        type="button"
                        className="knowledge-button knowledge-button-quiet"
                        onClick={() => setRenameDocument(null)}
                      >
                        Cancel
                      </button>

                      <button
                        type="submit"
                        className="knowledge-button knowledge-button-primary"
                        disabled={actionLoading || !renameValue.trim()}
                      >
                        {actionLoading ? "Saving..." : "Save changes"}
                      </button>
                    </footer>
                  </form>
                ) : (
                  <>
                    <div className="knowledge-processing-box">
                      <div className="knowledge-processing-heading">
                        <div>
                          <strong>Processing workflow</strong>
                          <p>Current status reported by the backend</p>
                        </div>
                        <StatusBadge status={getStatus(selectedDocument)} />
                      </div>
                      {[
                        {
                          key: "UPLOADED",
                          title: "Uploaded",
                          description:
                            "The document has been uploaded successfully.",
                        },
                        {
                          key: "INGESTING",
                          title: "Ingesting",
                          description:
                            "The document is being extracted and prepared.",
                        },
                        {
                          key: "INDEXING",
                          title: "Indexing",
                          description:
                            "The document is being prepared for retrieval.",
                        },
                        {
                          key: "READY",
                          title: "Ready",
                          description:
                            "Processing is complete and the document is ready for use.",
                        },
                      ].map((stage, index) => {
                        const status = getStatus(selectedDocument);
                        const isFailed = [
                          "FAILED",
                          "REJECTED",
                          "ERROR",
                        ].includes(status);
                        const stageRank = [
                          "UPLOADED",
                          "INGESTING",
                          "INDEXING",
                          "READY",
                        ].indexOf(stage.key);
                        const statusRank = [
                          "UPLOADED",
                          "INGESTING",
                          "INDEXING",
                          "READY",
                        ].indexOf(status);
                        const effectiveStatusRank =
                          statusRank >= 0
                            ? statusRank
                            : ["PENDING", "QUEUED", "PROCESSING"].includes(
                                  status,
                                )
                              ? 1
                              : -1;
                        const complete =
                          !isFailed && effectiveStatusRank >= stageRank;
                        const current =
                          !isFailed && effectiveStatusRank === stageRank;
                        return (
                          <div
                            className={`knowledge-processing-stage ${complete ? "is-complete" : ""} ${current ? "is-current" : ""}`}
                            key={stage.key}
                          >
                            <span className="knowledge-processing-marker">
                              {complete ? (
                                <CheckCircle2 size={16} />
                              ) : current ? (
                                <Clock3 size={16} />
                              ) : (
                                index + 1
                              )}
                            </span>
                            <div>
                              <strong>{stage.title}</strong>
                              <p>{stage.description}</p>
                            </div>
                          </div>
                        );
                      })}
                      {["FAILED", "REJECTED", "ERROR"].includes(
                        getStatus(selectedDocument),
                      ) && (
                        <div className="knowledge-processing-error">
                          <AlertCircle size={17} />
                          <div>
                            <strong>
                              {getStatus(selectedDocument) === "REJECTED"
                                ? "Document rejected"
                                : "Processing failed"}
                            </strong>
                            <p>
                              {selectedDocument.status_reason ||
                                selectedDocument.error_message ||
                                selectedDocument.error ||
                                "The backend has not provided a failure reason."}
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="knowledge-detail-list">
                      <div>
                        <span>Filename</span>

                        <strong>{getFilename(selectedDocument)}</strong>
                      </div>

                      <div>
                        <span>Document ID</span>

                        <strong>
                          {getDocumentId(selectedDocument) || "—"}
                        </strong>
                      </div>

                      <div>
                        <span>Project ID</span>

                        <strong>{selectedDocument.project_id || "—"}</strong>
                      </div>

                      <div>
                        <span>File size</span>

                        <strong>
                          {formatBytes(selectedDocument.size_bytes)}
                        </strong>
                      </div>

                      <div>
                        <span>MIME type</span>

                        <strong>{selectedDocument.mime_type || "—"}</strong>
                      </div>

                      <div>
                        <span>Created</span>

                        <strong>
                          {formatDate(selectedDocument.created_at)}
                        </strong>
                      </div>

                      <div>
                        <span>Document status</span>

                        <StatusBadge
                          status={String(
                            selectedDocument.status || "UNKNOWN",
                          ).toUpperCase()}
                        />
                      </div>

                      <div>
                        <span>Indexing status</span>

                        <StatusBadge status={getStatus(selectedDocument)} />
                      </div>

                      <div>
                        <span>Status reason</span>

                        <strong>
                          {selectedDocument.status_reason ||
                            "No reason reported"}
                        </strong>
                      </div>
                    </div>
                  </>
                )}
              </section>
            </div>,
            document.body,
          )}
      </div>
    </main>
  );
}
