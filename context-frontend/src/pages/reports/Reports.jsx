import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowDownToLine,
  BarChart3,
  CheckCircle2,
  Clock3,
  FileText,
  FolderKanban,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";

import { apiFetch } from "../../services/api";
import "./Reports.css";

/* -------------------- API helpers -------------------- */

async function fetchReportData(path) {
  const response = await apiFetch(path);

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));

    throw new Error(
      body.detail || body.message || `Request failed (${response.status})`,
    );
  }

  return response.json();
}

function unwrap(value) {
  let current = value;

  for (let i = 0; i < 6; i += 1) {
    if (Array.isArray(current)) return current;
    if (!current || typeof current !== "object") return current;

    const next =
      current.data ??
      current.items ??
      current.results ??
      current.projects ??
      current.documents;

    if (next === undefined || next === current) {
      return current;
    }

    current = next;
  }

  return current;
}

function getArray(response) {
  const result = unwrap(response);
  return Array.isArray(result) ? result : null;
}

function getCount(response) {
  const result = unwrap(response);

  if (Array.isArray(result)) {
    return result.length;
  }

  if (result && typeof result === "object") {
    const candidates = [
      result.total,
      result.total_count,
      result.count,
      result.total_items,
      result.total_records,
    ];

    for (const value of candidates) {
      if (
        value !== undefined &&
        value !== null &&
        value !== "" &&
        Number.isFinite(Number(value))
      ) {
        return Number(value);
      }
    }
  }

  return null;
}

function getStatus(item) {
  return String(
    item?.indexing_status ??
      item?.processing_status ??
      item?.status ??
      "Unknown",
  )
    .trim()
    .toLowerCase();
}

function formatStatus(status) {
  if (!status) return "Unknown";

  return String(status)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function downloadCSV(filename, rows) {
  if (!rows.length) return;

  const columns = Object.keys(rows[0]);

  const escapeCSV = (value) => {
    const text = String(value ?? "");
    return `"${text.replaceAll('"', '""')}"`;
  };

  const csv = [
    columns.map(escapeCSV).join(","),
    ...rows.map((row) =>
      columns.map((column) => escapeCSV(row[column])).join(","),
    ),
  ].join("\r\n");

  const blob = new Blob(["\uFEFF", csv], {
    type: "text/csv;charset=utf-8;",
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(url);
}

/* -------------------- UI components -------------------- */

function MetricCard({ icon: Icon, label, value, description, tone }) {
  return (
    <article className={`report-metric-card ${tone || ""}`}>
      <div className="report-metric-top">
        <span className="report-metric-icon">
          <Icon size={20} strokeWidth={1.8} />
        </span>

        <span className="report-metric-label">{label}</span>
      </div>

      <div className="report-metric-value">
        {value === null || value === undefined ? "—" : value}
      </div>

      <p className="report-metric-description">{description}</p>
    </article>
  );
}

function StatusBar({ label, count, total, colorClass }) {
  const percent = total > 0 ? Math.round((count / total) * 100) : 0;

  return (
    <div className="report-status-row">
      <div className="report-status-heading">
        <span>{label}</span>

        <span>
          {count} <small>({percent}%)</small>
        </span>
      </div>

      <div
        className="report-progress-track"
        role="progressbar"
        aria-label={`${label} documents`}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={count}
      >
        <div
          className={`report-progress-fill ${colorClass || ""}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

/* -------------------- Reports page -------------------- */

export default function Reports() {
  const [projects, setProjects] = useState([]);
  const [documents, setDocuments] = useState([]);

  const [projectCount, setProjectCount] = useState(null);
  const [documentCount, setDocumentCount] = useState(null);

  const [projectsAvailable, setProjectsAvailable] = useState(false);
  const [documentsAvailable, setDocumentsAvailable] = useState(false);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const loadReports = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError("");

    const documentParams = new URLSearchParams({
      page: "1",
      page_size: "100",
      sort_by: "created_at",
      order: "desc",
    });

    const results = await Promise.allSettled([
      fetchReportData("/projects/"),
      fetchReportData(`/upload/documents?${documentParams.toString()}`),
    ]);

    const [projectResult, documentResult] = results;

    /* Projects response */

    if (projectResult.status === "fulfilled") {
      const response = projectResult.value;
      const list = getArray(response);
      const count = getCount(response);

      setProjectsAvailable(list !== null || count !== null);
      setProjects(list ?? []);
      setProjectCount(count ?? (list ? list.length : null));
    } else {
      console.error("Reports: failed to load projects:", projectResult.reason);

      setProjectsAvailable(false);
      setProjects([]);
      setProjectCount(null);
    }

    /* Documents response */

    if (documentResult.status === "fulfilled") {
      const response = documentResult.value;
      const list = getArray(response);
      const count = getCount(response);

      setDocumentsAvailable(list !== null || count !== null);
      setDocuments(list ?? []);
      setDocumentCount(count ?? (list ? list.length : null));
    } else {
      console.error(
        "Reports: failed to load documents:",
        documentResult.reason,
      );

      setDocumentsAvailable(false);
      setDocuments([]);
      setDocumentCount(null);
    }

    /* Error messages */

    if (
      projectResult.status === "rejected" &&
      documentResult.status === "rejected"
    ) {
      setError(
        "Reports could not load. Check your API endpoints, login session, and backend connection.",
      );
    } else if (
      projectResult.status === "rejected" ||
      documentResult.status === "rejected"
    ) {
      setError(
        "Some report data could not be loaded. Available sections are still shown.",
      );
    } else if (
      (projectResult.status === "fulfilled" &&
        getArray(projectResult.value) === null &&
        getCount(projectResult.value) === null) ||
      (documentResult.status === "fulfilled" &&
        getArray(documentResult.value) === null &&
        getCount(documentResult.value) === null)
    ) {
      setError(
        "An API returned a response, but its data structure was not recognized. Check the browser console for details.",
      );
    }

    setLastUpdated(new Date());
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  /* Project search and filtering */

  const projectRows = useMemo(() => {
    const query = search.trim().toLowerCase();

    return projects.filter((project) => {
      const name = String(
        project.name ?? project.project_name ?? "",
      ).toLowerCase();

      const id = String(project.project_id ?? project.id ?? "").toLowerCase();

      const status = getStatus(project);

      const matchesSearch =
        !query || name.includes(query) || id.includes(query);

      const matchesStatus = statusFilter === "all" || status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [projects, search, statusFilter]);

  /* Document status statistics */

  const documentStats = useMemo(() => {
    const stats = {
      processed: 0,
      processing: 0,
      failed: 0,
      unknown: 0,
    };

    for (const document of documents) {
      const status = getStatus(document);

      if (
        ["completed", "processed", "indexed", "success", "succeeded"].includes(
          status,
        )
      ) {
        stats.processed += 1;
      } else if (
        [
          "processing",
          "pending",
          "queued",
          "in_progress",
          "uploading",
        ].includes(status)
      ) {
        stats.processing += 1;
      } else if (["failed", "error", "rejected"].includes(status)) {
        stats.failed += 1;
      } else {
        stats.unknown += 1;
      }
    }

    return stats;
  }, [documents]);

  /* File types */

  const fileTypes = useMemo(() => {
    const counts = {};

    for (const document of documents) {
      const type = String(
        document.file_type ??
          document.file_extension ??
          document.extension ??
          document.content_type ??
          "Unknown",
      )
        .replace(/^\./, "")
        .toUpperCase();

      counts[type] = (counts[type] || 0) + 1;
    }

    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [documents]);

  /* CSV exports */

  const exportProjects = () => {
    downloadCSV(
      "inferai-project-report.csv",
      projectRows.map((project) => ({
        Project_ID: project.project_id ?? project.id ?? "",
        Project_Name: project.name ?? project.project_name ?? "",
        Status: project.status ?? "",
        Created_At: project.created_at ?? "",
      })),
    );
  };

  const exportDocuments = () => {
    downloadCSV(
      "inferai-document-report.csv",
      documents.map((document) => ({
        Document_ID: document.id ?? document.document_id ?? "",
        Document_Name:
          document.name ?? document.filename ?? document.file_name ?? "",
        File_Type: document.file_type ?? document.file_extension ?? "",
        Status: document.status ?? "",
        Indexing_Status: document.indexing_status ?? "",
        Created_At: document.created_at ?? "",
      })),
    );
  };

  const exportSummary = () => {
    downloadCSV("inferai-workspace-summary.csv", [
      {
        Report: "Workspace Summary",
        Projects: projectCount ?? "Unavailable",
        Documents: documentCount ?? "Unavailable",
        Processed_Documents: documentsAvailable
          ? documentStats.processed
          : "Unavailable",
        Processing_Documents: documentsAvailable
          ? documentStats.processing
          : "Unavailable",
        Failed_Documents: documentsAvailable
          ? documentStats.failed
          : "Unavailable",
        Generated_At: new Date().toISOString(),
      },
    ]);
  };

  /* Loading state */

  if (loading) {
    return (
      <main className="reports-page">
        <div className="reports-loading">
          <LoaderCircle size={28} className="reports-spinner" />
          <p>Preparing your workspace reports…</p>
        </div>
      </main>
    );
  }

  /* Main page */

  return (
    <main className="reports-page">
      <header className="reports-page-header">
        <div>
          <div className="reports-eyebrow">
            <span className="reports-eyebrow-line" />
            INSIGHTS &amp; ANALYTICS
          </div>

          <h1>Workspace Reports</h1>

          <p className="reports-subtitle">
            Understand your projects, documents, and knowledge workspace at a
            glance.
          </p>

          <p className="reports-updated">
            {lastUpdated
              ? `Last updated ${lastUpdated.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}`
              : "Not updated yet"}
          </p>
        </div>

        <div className="reports-header-actions">
          <button
            type="button"
            className="reports-button reports-button-secondary"
            onClick={() => loadReports(true)}
            disabled={refreshing}
          >
            <RefreshCw
              size={16}
              className={refreshing ? "reports-spinner" : ""}
            />
            Refresh
          </button>

          <button
            type="button"
            className="reports-button reports-button-primary"
            onClick={exportSummary}
          >
            <ArrowDownToLine size={17} />
            Export summary
          </button>
        </div>
      </header>

      {error && (
        <div className="reports-alert" role="status">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* Overview */}

      <section className="reports-section">
        <div className="reports-section-heading">
          <div>
            <span className="reports-section-kicker">OVERVIEW</span>
            <h2>Workspace at a glance</h2>
          </div>

          <span className="reports-live-label">
            <span className="reports-live-dot" />
            API data
          </span>
        </div>

        <div className="reports-metrics-grid">
          <MetricCard
            icon={FolderKanban}
            label="Total projects"
            value={projectCount}
            description={
              projectsAvailable
                ? "Projects returned by the API"
                : "Project data unavailable"
            }
            tone="copper"
          />

          <MetricCard
            icon={FileText}
            label="Total documents"
            value={documentCount}
            description={
              documentsAvailable
                ? "Documents returned by the API"
                : "Document data unavailable"
            }
            tone="violet"
          />

          <MetricCard
            icon={CheckCircle2}
            label="Processed documents"
            value={documentsAvailable ? documentStats.processed : null}
            description="Completed or indexed in loaded results"
            tone="green"
          />

          <MetricCard
            icon={Activity}
            label="Processing issues"
            value={documentsAvailable ? documentStats.failed : null}
            description="Failed or rejected in loaded results"
            tone="rose"
          />
        </div>

        <p className="reports-footnote">
          Document status analytics use the documents returned by the current
          API request. If the API paginates results, status breakdowns may
          represent only the loaded page.
        </p>
      </section>

      {/* Document analytics */}

      <section className="reports-content-grid">
        <article className="reports-panel">
          <div className="reports-panel-heading">
            <div className="reports-panel-title-icon">
              <BarChart3 size={19} />
            </div>

            <div>
              <h2>Document processing</h2>
              <p>Processing status of loaded documents</p>
            </div>
          </div>

          {documentsAvailable ? (
            <div className="reports-status-chart">
              <StatusBar
                label="Processed"
                count={documentStats.processed}
                total={documents.length}
                colorClass="progress-green"
              />

              <StatusBar
                label="In progress"
                count={documentStats.processing}
                total={documents.length}
                colorClass="progress-copper"
              />

              <StatusBar
                label="Failed"
                count={documentStats.failed}
                total={documents.length}
                colorClass="progress-rose"
              />

              {documentStats.unknown > 0 && (
                <StatusBar
                  label="Unknown status"
                  count={documentStats.unknown}
                  total={documents.length}
                  colorClass="progress-muted"
                />
              )}

              {documents.length === 0 && (
                <div className="reports-empty-inline">
                  No documents were returned by the API.
                </div>
              )}
            </div>
          ) : (
            <div className="reports-unavailable">
              <AlertCircle size={20} />
              <span>Document processing data is unavailable.</span>
            </div>
          )}
        </article>

        <article className="reports-panel">
          <div className="reports-panel-heading">
            <div className="reports-panel-title-icon">
              <FileText size={19} />
            </div>

            <div>
              <h2>File type breakdown</h2>
              <p>Formats represented in loaded documents</p>
            </div>
          </div>

          {documentsAvailable && fileTypes.length > 0 ? (
            <div className="reports-file-types">
              {fileTypes.slice(0, 6).map(([type, count], index) => (
                <div className="reports-file-type" key={type}>
                  <span className={`reports-file-type-icon type-${index % 4}`}>
                    <FileText size={17} />
                  </span>

                  <span className="reports-file-type-name">{type}</span>

                  <span className="reports-file-type-count">{count}</span>

                  <div className="reports-file-type-track">
                    <span
                      style={{
                        width: `${
                          documents.length
                            ? (count / documents.length) * 100
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="reports-empty-inline">
              {documentsAvailable
                ? "No file type information is available yet."
                : "File type data is unavailable."}
            </div>
          )}
        </article>
      </section>

      {/* Project directory */}

      <section className="reports-section reports-project-section">
        <div className="reports-section-heading reports-project-heading">
          <div>
            <span className="reports-section-kicker">PROJECT INSIGHTS</span>

            <h2>Project directory</h2>

            <p>
              Review the project records currently available to your account.
            </p>
          </div>

          <button
            type="button"
            className="reports-button reports-button-secondary"
            onClick={exportProjects}
            disabled={!projectsAvailable || projects.length === 0}
          >
            <ArrowDownToLine size={16} />
            Export projects
          </button>
        </div>

        <div className="reports-table-toolbar">
          <div className="reports-search">
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search project name or ID…"
              aria-label="Search projects"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            aria-label="Filter projects by status"
          >
            <option value="all">All statuses</option>

            {[...new Set(projects.map((project) => getStatus(project)))]
              .filter((status) => status !== "unknown")
              .sort()
              .map((status) => (
                <option key={status} value={status}>
                  {formatStatus(status)}
                </option>
              ))}
          </select>
        </div>

        {!projectsAvailable ? (
          <div className="reports-table-state">
            <AlertCircle size={22} />
            <strong>Project report unavailable</strong>
            <p>The projects API did not return usable project data.</p>
          </div>
        ) : projectRows.length === 0 ? (
          <div className="reports-table-state">
            <FolderKanban size={24} />
            <strong>No matching projects</strong>
            <p>Try a different search or status filter.</p>
          </div>
        ) : (
          <div className="reports-table-scroll">
            <table className="reports-table">
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Project ID</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>

              <tbody>
                {projectRows.map((project, index) => {
                  const status = getStatus(project);

                  const name =
                    project.name ?? project.project_name ?? "Untitled project";

                  const id = project.project_id ?? project.id ?? "—";

                  return (
                    <tr key={`${id}-${index}`}>
                      <td>
                        <div className="reports-project-name">
                          <span className="reports-project-avatar">
                            {String(name).charAt(0).toUpperCase()}
                          </span>

                          <span>{name}</span>
                        </div>
                      </td>

                      <td className="reports-id-cell">{id}</td>

                      <td>
                        <span
                          className={`reports-status-pill status-${status.replace(
                            /[^a-z0-9-]/g,
                            "-",
                          )}`}
                        >
                          <span />
                          {formatStatus(status)}
                        </span>
                      </td>

                      <td>{formatDate(project.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {projectsAvailable && (
          <div className="reports-table-footer">
            Showing {projectRows.length} of {projects.length} loaded projects
          </div>
        )}
      </section>

      {/* Additional analytics */}

      <section className="reports-section">
        <div className="reports-section-heading">
          <div>
            <span className="reports-section-kicker">PLATFORM HEALTH</span>

            <h2>Additional analytics</h2>
          </div>
        </div>

        <div className="reports-analytics-grid">
          <article className="reports-analytics-card">
            <div className="reports-analytics-icon">
              <TrendingUp size={19} />
            </div>

            <div>
              <h3>AI &amp; retrieval analytics</h3>

              <p>
                Query volume, retrieval success, and response latency require a
                connected analytics endpoint.
              </p>

              <span className="reports-not-connected">
                <Clock3 size={13} />
                Data source not connected
              </span>
            </div>
          </article>

          <article className="reports-analytics-card">
            <div className="reports-analytics-icon">
              <ShieldCheck size={19} />
            </div>

            <div>
              <h3>Security &amp; audit reports</h3>

              <p>
                Login events, permission changes, and access denials require an
                audit-log endpoint.
              </p>

              <span className="reports-not-connected">
                <Clock3 size={13} />
                Data source not connected
              </span>
            </div>
          </article>
        </div>
      </section>

      <footer className="reports-footer">
        <span className="reports-footer-mark">
          <Activity size={15} />
        </span>

        <span>CONTEXTAPI REPORTS</span>
        <span className="reports-footer-separator">·</span>
        <span>Workspace intelligence</span>
      </footer>
    </main>
  );
}
