import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Folder,
  FileText,
  CloudUpload,
  AppWindow,
  Plus,
  ArrowRight,
  ChartColumn,
  Database,
  Sparkles,
  RefreshCw,
  Info,
  FileSpreadsheet,
  File,
  CheckCircle2,
  Clock3,
  AlertCircle,
} from "lucide-react";

import "./Dashboard.css";
import { apiFetch } from "../../services/api";

const DOCUMENT_TYPES = [
  { label: "PDF", extensions: ["pdf"], color: "#bd6e30" },
  { label: "Word", extensions: ["doc", "docx"], color: "#efa94e" },
  { label: "Excel", extensions: ["xls", "xlsx", "csv"], color: "#438b70" },
  { label: "PowerPoint", extensions: ["ppt", "pptx"], color: "#ad7ac3" },
  { label: "Text", extensions: ["txt", "md"], color: "#639cc3" },
];

const ACTIONS = [
  {
    title: "Create Project",
    description: "Start a project and organize your work",
    icon: Plus,
    path: "/projects/create",
    tone: "orange",
  },
  {
    title: "Upload Documents",
    description: "Add files to your knowledge base",
    icon: CloudUpload,
    path: "/knowledge",
    tone: "green",
  },
  {
    title: "Manage Applications",
    description: "Configure your target applications",
    icon: AppWindow,
    path: "/target-applications",
    tone: "purple",
  },
  {
    title: "Explore Knowledge",
    description: "Search your enterprise knowledge",
    icon: Sparkles,
    path: "/knowledge",
    tone: "amber",
  },
];

const METRICS = [
  {
    title: "Total Projects",
    description: "Projects in your workspace",
    icon: Folder,
    tone: "orange",
    path: "/projects",
  },
  {
    title: "Total Documents",
    description: "Documents in your knowledge base",
    icon: FileText,
    tone: "purple",
    path: "/knowledge",
  },
  {
    title: "Recent Uploads",
    description: "Recently uploaded files",
    icon: CloudUpload,
    tone: "green",
    path: "/knowledge",
  },
  {
    title: "Target Applications",
    description: "Connected applications",
    icon: AppWindow,
    tone: "amber",
    path: "/target-applications",
  },
];

async function apiRequest(path, options = {}) {
  const response = await apiFetch(path, {
    headers: {
      Accept: "application/json",
      ...options.headers,
    },
    ...options,
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

function getDocumentsFromResponse(result) {
  if (Array.isArray(result)) return result;

  const candidates = [
    result?.documents,
    result?.items,
    result?.results,
    result?.data?.documents,
    result?.data?.items,
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate;
  }

  throw new Error("The documents API returned an unexpected response format.");
}

function getProjectsFromResponse(result) {
  if (Array.isArray(result)) return result;

  const candidates = [
    result?.projects,
    result?.items,
    result?.results,
    result?.data?.projects,
    result?.data?.items,
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate;
  }

  throw new Error("The projects API returned an unexpected response format.");
}

function getDocumentId(document) {
  return document?.document_id ?? document?.id ?? "";
}

function getProjectId(project) {
  return project?.project_id ?? project?.id ?? "";
}

function getDocumentName(document) {
  return (
    document?.original_filename ||
    document?.name ||
    document?.filename ||
    document?.file_name ||
    ""
  );
}

function getProjectName(project) {
  return (
    project?.name ||
    project?.project_name ||
    project?.title ||
    getProjectId(project) ||
    "Untitled project"
  );
}

function getDocumentExtension(document) {
  const filename = getDocumentName(document);

  const rawType =
    document?.file_type ||
    document?.mime_type ||
    document?.extension ||
    filename.split(".").pop() ||
    "";

  const value = String(rawType).toLowerCase().replace(/^\./, "");

  const mimeTypes = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
      "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "text/plain": "txt",
    "text/markdown": "md",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation":
      "pptx",
  };

  return mimeTypes[value] || value;
}

function getDocumentDate(document) {
  return (
    document?.created_at ||
    document?.uploaded_at ||
    document?.upload_date ||
    null
  );
}

function getProjectDate(project) {
  return project?.created_at || project?.updated_at || null;
}

function getStatus(document) {
  return String(
    document?.indexing_status || document?.status || "UNKNOWN",
  ).toUpperCase();
}

function getUploadStatus(document) {
  const status = getStatus(document);

  if (["FAILED", "ERROR", "REJECTED"].includes(status)) {
    return { label: "Failed", className: "failed" };
  }

  if (
    [
      "INGESTING",
      "INDEXING",
      "PROCESSING",
      "PENDING",
      "QUEUED",
      "IN_PROGRESS",
    ].includes(status)
  ) {
    return { label: "Processing", className: "processing" };
  }

  if (
    [
      "READY",
      "COMPLETED",
      "SUCCESS",
      "SUCCEEDED",
      "INDEXED",
      "ACTIVE",
    ].includes(status)
  ) {
    return { label: "Completed", className: "completed" };
  }

  return { label: "Status unavailable", className: "unknown" };
}

function formatDate(value) {
  if (!value) return "Date unavailable";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "Date unavailable";

  return date.toLocaleString();
}

function Dashboard() {
  const navigate = useNavigate();

  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState("");

  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState("");

  const loadDocuments = useCallback(async (signal) => {
    setDocumentsLoading(true);
    setDocumentsError("");

    try {
      const allDocuments = [];
      let page = 1;
      let totalPages = 1;

      do {
        const params = new URLSearchParams({
          page: String(page),
          page_size: "100",
          sort_by: "created_at",
          order: "desc",
        });

        const response = await apiRequest(
          `/upload/documents?${params.toString()}`,
          { signal },
        );

        const result = unwrap(response);
        const pageDocuments = getDocumentsFromResponse(result);

        allDocuments.push(...pageDocuments);

        totalPages = Math.max(1, Number(result?.pagination?.total_pages ?? 1));

        page += 1;
      } while (page <= totalPages && !signal?.aborted);

      if (!signal?.aborted) {
        setDocuments(allDocuments);
      }
    } catch (error) {
      if (error.name !== "AbortError" && !signal?.aborted) {
        setDocuments([]);
        setDocumentsError(error.message || "Unable to load documents.");
      }
    } finally {
      if (!signal?.aborted) {
        setDocumentsLoading(false);
      }
    }
  }, []);

  const loadProjects = useCallback(async (signal) => {
    setProjectsLoading(true);
    setProjectsError("");

    try {
      const response = await apiRequest("/projects/", { signal });
      const result = unwrap(response);

      if (!signal?.aborted) {
        setProjects(getProjectsFromResponse(result));
      }
    } catch (error) {
      if (error.name !== "AbortError" && !signal?.aborted) {
        setProjects([]);
        setProjectsError(error.message || "Unable to load projects.");
      }
    } finally {
      if (!signal?.aborted) {
        setProjectsLoading(false);
      }
    }
  }, []);

  const refreshDashboard = useCallback(async () => {
    const controller = new AbortController();

    await Promise.all([
      loadDocuments(controller.signal),
      loadProjects(controller.signal),
    ]);
  }, [loadDocuments, loadProjects]);

  useEffect(() => {
    const controller = new AbortController();

    loadDocuments(controller.signal);
    loadProjects(controller.signal);

    return () => controller.abort();
  }, [loadDocuments, loadProjects]);

  const totalDocuments = documents.length;
  const totalProjects = projects.length;

  const documentTypeCounts = useMemo(
    () =>
      DOCUMENT_TYPES.map((type) => ({
        ...type,
        count: documents.filter((document) =>
          type.extensions.includes(getDocumentExtension(document)),
        ).length,
      })),
    [documents],
  );

  const otherCount = useMemo(
    () =>
      documents.filter((document) => {
        const extension = getDocumentExtension(document);

        return !DOCUMENT_TYPES.some((type) =>
          type.extensions.includes(extension),
        );
      }).length,
    [documents],
  );

  const chartItems = useMemo(
    () => [
      ...documentTypeCounts,
      { label: "Other", color: "#b7a795", count: otherCount },
    ],
    [documentTypeCounts, otherCount],
  );

  const chartGradient = useMemo(() => {
    if (!totalDocuments) return "";

    let currentAngle = 0;

    return chartItems
      .filter((item) => item.count > 0)
      .map((item) => {
        const start = currentAngle;

        currentAngle += (item.count / totalDocuments) * 360;

        return `${item.color} ${start}deg ${currentAngle}deg`;
      })
      .join(", ");
  }, [chartItems, totalDocuments]);

  const recentDocuments = useMemo(
    () =>
      [...documents]
        .sort((a, b) => {
          const dateA = new Date(getDocumentDate(a) || 0).getTime();
          const dateB = new Date(getDocumentDate(b) || 0).getTime();

          return dateB - dateA;
        })
        .slice(0, 5),
    [documents],
  );

  const recentProjects = useMemo(
    () =>
      [...projects]
        .sort((a, b) => {
          const dateA = new Date(getProjectDate(a) || 0).getTime();
          const dateB = new Date(getProjectDate(b) || 0).getTime();

          return dateB - dateA;
        })
        .slice(0, 5),
    [projects],
  );

  const knowledgeStats = useMemo(() => {
    const readyStatuses = [
      "READY",
      "COMPLETED",
      "SUCCESS",
      "SUCCEEDED",
      "INDEXED",
      "ACTIVE",
    ];

    const processingStatuses = [
      "INGESTING",
      "INDEXING",
      "PROCESSING",
      "PENDING",
      "QUEUED",
      "IN_PROGRESS",
    ];

    const failedStatuses = ["FAILED", "REJECTED", "ERROR"];

    return {
      total: documents.length,
      ready: documents.filter((doc) => readyStatuses.includes(getStatus(doc)))
        .length,
      processing: documents.filter((doc) =>
        processingStatuses.includes(getStatus(doc)),
      ).length,
      failed: documents.filter((doc) => failedStatuses.includes(getStatus(doc)))
        .length,
    };
  }, [documents]);

  const activityDays = useMemo(() => {
    const days = [];

    for (let offset = 6; offset >= 0; offset -= 1) {
      const date = new Date();

      date.setHours(0, 0, 0, 0);
      date.setDate(date.getDate() - offset);

      const nextDay = new Date(date);
      nextDay.setDate(nextDay.getDate() + 1);

      const uploads = documents.filter((document) => {
        const rawDate = getDocumentDate(document);

        if (!rawDate) return false;

        const createdAt = new Date(rawDate);

        return createdAt >= date && createdAt < nextDay;
      }).length;

      const createdProjects = projects.filter((project) => {
        const rawDate = getProjectDate(project);

        if (!rawDate) return false;

        const createdAt = new Date(rawDate);

        return createdAt >= date && createdAt < nextDay;
      }).length;

      days.push({
        label: date.toLocaleDateString("en-IN", { weekday: "short" }),
        uploads,
        projects: createdProjects,
        date,
      });
    }

    return days;
  }, [documents, projects]);

  const maxActivity = Math.max(
    1,
    ...activityDays.map((day) => Math.max(day.uploads, day.projects)),
  );

  const metrics = METRICS.map((metric) => {
    let value = null;

    if (metric.title === "Total Projects") {
      value = projectsError ? null : totalProjects;
    } else if (metric.title === "Total Documents") {
      value = documentsError ? null : totalDocuments;
    } else if (metric.title === "Recent Uploads") {
      value = documentsError ? null : recentDocuments.length;
    }

    return { ...metric, value };
  });

  function openDocument(document) {
    const id = getDocumentId(document);

    if (id) {
      navigate(`/knowledge?view=ALL`);
    } else {
      navigate("/knowledge");
    }
  }

  function openProject(project) {
    const id = getProjectId(project);

    if (id) {
      navigate(`/projects/${encodeURIComponent(id)}`);
    } else {
      navigate("/projects");
    }
  }

  return (
    <main className="infer-dashboard">
      <section className="dashboard-hero">
        <div className="hero-content">
          <span className="hero-eyebrow">WELCOME TO CONTEXTAPI</span>

          <h1>
            Turn Information
            <br />
            into <em>Intelligent Action</em>
          </h1>

          <p>
            Manage projects, explore knowledge and build with AI — all in one
            place.
          </p>
        </div>
      </section>

      <section className="dashboard-actions">
        {ACTIONS.map(({ title, description, icon: Icon, path, tone }) => (
          <button
            type="button"
            className={`quick-action ${tone}`}
            key={title}
            onClick={() => navigate(path)}
          >
            <span className="action-icon">
              <Icon size={25} />
            </span>

            <span className="action-copy">
              <strong>{title}</strong>
              <small>{description}</small>
            </span>

            <span className="action-arrow">
              <ArrowRight size={19} />
            </span>
          </button>
        ))}
      </section>

      <section className="dashboard-metrics">
        {metrics.map(
          ({ title, description, icon: Icon, tone, path, value }) => (
            <button
              type="button"
              className="metric-card"
              key={title}
              onClick={() => navigate(path)}
            >
              <span className={`metric-icon ${tone}`}>
                <Icon size={25} />
              </span>

              <span className="metric-content">
                <small>{title}</small>

                <strong className="metric-empty-value">
                  {value === null
                    ? "—"
                    : title === "Recent Uploads"
                      ? value
                      : value}
                </strong>

                <small className="metric-note">
                  {title === "Total Projects" && projectsError
                    ? "Unable to retrieve project count"
                    : title === "Total Documents" && documentsError
                      ? "Unable to retrieve document count"
                      : title === "Recent Uploads" && documentsError
                        ? "Unable to retrieve upload count"
                        : description}
                </small>
              </span>

              <span className="metric-link">
                <ArrowRight size={16} />
              </span>
            </button>
          ),
        )}
      </section>

      <section className="dashboard-analytics">
        <article className="dashboard-panel activity-panel">
          <div className="panel-heading">
            <h2>
              <ChartColumn size={22} />
              Project Activity
            </h2>

            <button
              type="button"
              className="chart-refresh"
              onClick={refreshDashboard}
              disabled={documentsLoading || projectsLoading}
              aria-label="Refresh project activity"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
          </div>

          {documentsLoading || projectsLoading ? (
            <div className="dashboard-empty-state">
              Loading workspace activity...
            </div>
          ) : documentsError && projectsError ? (
            <div className="dashboard-empty-state">
              <Info size={25} />
              <strong>Activity unavailable</strong>
              <p>
                Project and document data could not be loaded. Refresh to try
                again.
              </p>
            </div>
          ) : (
            <>
              <div className="chart-legend">
                <span>
                  <i className="legend-upload" />
                  Document uploads
                </span>
                <span>
                  <i className="legend-request" />
                  Projects created
                </span>
              </div>

              <div className="activity-chart">
                <div className="chart-y-labels">
                  <span>{maxActivity}</span>
                  <span>{Math.ceil(maxActivity * 0.75)}</span>
                  <span>{Math.ceil(maxActivity * 0.5)}</span>
                  <span>{Math.ceil(maxActivity * 0.25)}</span>
                  <span>0</span>
                </div>

                <div className="chart-bars-area">
                  {[0, 1, 2, 3, 4].map((line) => (
                    <i className="chart-gridline" key={line} />
                  ))}

                  {activityDays.map((day) => (
                    <div
                      className="chart-day"
                      key={day.date.toISOString()}
                      title={`${day.label}: ${day.uploads} uploads, ${day.projects} projects created`}
                    >
                      <div className="bar-pair">
                        <span
                          className="bar-upload"
                          style={{
                            height: `${(day.uploads / maxActivity) * 100}%`,
                            minHeight: day.uploads ? 5 : 0,
                          }}
                        />
                        <span
                          className="bar-request"
                          style={{
                            height: `${(day.projects / maxActivity) * 100}%`,
                            minHeight: day.projects ? 5 : 0,
                          }}
                        />
                      </div>
                      <small>{day.label}</small>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </article>

        <article className="dashboard-panel document-panel">
          <div className="panel-heading">
            <h2>Document Types</h2>

            <button
              type="button"
              className="chart-refresh"
              onClick={() => loadDocuments()}
              disabled={documentsLoading}
              aria-label="Refresh document types"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
          </div>

          {documentsLoading ? (
            <div className="document-chart-message">
              Loading document types...
            </div>
          ) : documentsError ? (
            <div className="document-chart-message">
              <Info size={25} />
              <p>{documentsError}</p>
              <button type="button" onClick={() => loadDocuments()}>
                Retry
              </button>
            </div>
          ) : (
            <>
              <div className="document-chart-content">
                <div
                  className="donut-chart"
                  style={{
                    background: totalDocuments
                      ? `conic-gradient(${chartGradient})`
                      : "var(--line)",
                  }}
                  role="img"
                  aria-label={`${totalDocuments} documents classified by type`}
                >
                  <div className="donut-hole">
                    <strong>{totalDocuments}</strong>
                    <span>Documents</span>
                  </div>
                </div>

                <div className="document-legend">
                  {chartItems.map((item) => (
                    <div className="document-legend-row" key={item.label}>
                      <i style={{ background: item.color }} />
                      <span>{item.label}</span>
                      <strong>{item.count}</strong>
                    </div>
                  ))}
                </div>
              </div>

              <p className="document-chart-caption">
                File counts are calculated from the documents returned by the
                API.
              </p>
            </>
          )}
        </article>

        <article className="dashboard-panel storage-panel">
          <div className="panel-heading">
            <h2>Workspace Knowledge</h2>
          </div>

          {documentsLoading ? (
            <div className="dashboard-empty-state">
              <Database size={30} />
              <strong>Loading knowledge statistics</strong>
              <p>Retrieving document indexing statuses from the backend.</p>
            </div>
          ) : documentsError ? (
            <div className="dashboard-empty-state">
              <Info size={30} />
              <strong>Knowledge data unavailable</strong>
              <p>{documentsError}</p>
              <button
                type="button"
                className="dashboard-inline-link"
                onClick={() => loadDocuments()}
              >
                Retry <RefreshCw size={15} />
              </button>
            </div>
          ) : (
            <>
              <div className="storage-overview">
                <span className="storage-main-icon">
                  <Database size={25} />
                </span>

                <div>
                  <strong>{knowledgeStats.total} documents</strong>
                  <p>Current document records</p>
                </div>
              </div>

              <div className="storage-detail-row">
                <span>
                  <CheckCircle2 size={14} /> Search ready
                </span>
                <strong>{knowledgeStats.ready}</strong>
              </div>

              <div className="storage-detail-row">
                <span>
                  <Clock3 size={14} /> Processing
                </span>
                <strong>{knowledgeStats.processing}</strong>
              </div>

              <div className="storage-detail-row">
                <span>
                  <AlertCircle size={14} /> Needs attention
                </span>
                <strong>{knowledgeStats.failed}</strong>
              </div>

              <button
                type="button"
                className="dashboard-inline-link"
                onClick={() => navigate("/knowledge")}
              >
                Explore knowledge <ArrowRight size={16} />
              </button>
            </>
          )}
        </article>
      </section>

      <section className="dashboard-bottom-grid">
        <article className="dashboard-panel recent-panel">
          <div className="panel-heading">
            <h2>Recent Projects</h2>

            <button type="button" onClick={() => navigate("/projects")}>
              View all <ArrowRight size={17} />
            </button>
          </div>

          {projectsLoading ? (
            <div className="dashboard-empty-state compact-empty">
              Loading projects...
            </div>
          ) : projectsError ? (
            <div className="dashboard-empty-state compact-empty">
              <Info size={25} />
              <strong>Projects unavailable</strong>
              <p>{projectsError}</p>

              <button
                type="button"
                className="dashboard-inline-link"
                onClick={() => loadProjects()}
              >
                Retry <RefreshCw size={15} />
              </button>
            </div>
          ) : recentProjects.length === 0 ? (
            <div className="dashboard-empty-state compact-empty">
              <Folder size={27} />
              <strong>No projects found</strong>
              <p>Create a project to start organizing your documents.</p>

              <button
                type="button"
                className="dashboard-inline-link"
                onClick={() => navigate("/projects/create")}
              >
                Create project <ArrowRight size={16} />
              </button>
            </div>
          ) : (
            <div className="recent-list">
              {recentProjects.map((project, index) => {
                const id = getProjectId(project);

                return (
                  <button
                    type="button"
                    className="project-row"
                    key={id || `${getProjectName(project)}-${index}`}
                    onClick={() => openProject(project)}
                  >
                    <span className="project-thumbnail">
                      <Folder size={22} />
                    </span>

                    <span className="recent-item-copy">
                      <strong title={getProjectName(project)}>
                        {getProjectName(project)}
                      </strong>
                      <small>{project.status || "Project"}</small>
                    </span>

                    <span className="metric-link">
                      <ArrowRight size={16} />
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </article>

        <article className="dashboard-panel recent-panel">
          <div className="panel-heading">
            <h2>Recent Uploads</h2>

            <button type="button" onClick={() => navigate("/knowledge")}>
              View all <ArrowRight size={17} />
            </button>
          </div>

          {documentsLoading ? (
            <div className="dashboard-empty-state compact-empty">
              Loading documents...
            </div>
          ) : documentsError ? (
            <div className="dashboard-empty-state compact-empty">
              <Info size={25} />
              <strong>Uploads unavailable</strong>
              <p>{documentsError}</p>
            </div>
          ) : recentDocuments.length === 0 ? (
            <div className="dashboard-empty-state compact-empty">
              <CloudUpload size={27} />
              <strong>No documents found</strong>
              <p>Uploaded documents will appear here.</p>

              <button
                type="button"
                className="dashboard-inline-link"
                onClick={() => navigate("/knowledge")}
              >
                Upload documents <ArrowRight size={16} />
              </button>
            </div>
          ) : (
            <div className="recent-list">
              {recentDocuments.map((document, index) => {
                const name = getDocumentName(document) || "Untitled document";
                const status = getUploadStatus(document);
                const key = getDocumentId(document) || `${name}-${index}`;

                const extension = getDocumentExtension(document);

                const Icon = ["xlsx", "xls", "csv"].includes(extension)
                  ? FileSpreadsheet
                  : ["pdf", "doc", "docx"].includes(extension)
                    ? FileText
                    : File;

                return (
                  <button
                    type="button"
                    className="upload-row upload-row-button"
                    key={key}
                    onClick={() => openDocument(document)}
                  >
                    <span className="file-icon">
                      <Icon size={21} />
                    </span>

                    <span className="recent-item-copy">
                      <strong title={name}>{name}</strong>
                      <small>{formatDate(getDocumentDate(document))}</small>
                    </span>

                    <span className={`upload-status ${status.className}`}>
                      {status.label}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </article>
      </section>

      <footer className="dashboard-footer">
        CONTEXTAPI <span>•</span> ENTERPRISE AI ASSISTANT
      </footer>
    </main>
  );
}

export default Dashboard;
