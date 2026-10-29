import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  Search as SearchIcon,
  FolderKanban,
  FileText,
  ArrowRight,
  ArrowLeft,
  LoaderCircle,
  AlertCircle,
  X,
} from "lucide-react";
import { apiFetch } from "../../services/api";
import "./Search.css";

function unwrap(payload) {
  return payload?.data ?? payload;
}

function getArray(payload, key) {
  const data = unwrap(payload);

  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.[key])) return data[key];
  if (Array.isArray(data?.items)) return data.items;

  return [];
}

function getProjectId(project) {
  return String(project?.project_id ?? project?.id ?? project?.projectId ?? "");
}

function getProjectName(project) {
  return (
    project?.name ??
    project?.project_name ??
    project?.projectName ??
    project?.title ??
    "Untitled project"
  );
}

function getDocumentId(document) {
  return String(
    document?.document_id ?? document?.id ?? document?.upload_id ?? "",
  );
}

function getDocumentName(document) {
  return (
    document?.original_filename ??
    document?.filename ??
    document?.file_name ??
    document?.name ??
    "Unnamed document"
  );
}

function getErrorMessage(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;

  if (Array.isArray(payload?.detail)) {
    return payload.detail.map((item) => item.msg).join(", ");
  }

  return payload?.message || fallback;
}

export default function SearchPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const query = searchParams.get("q") || "";

  const [input, setInput] = useState(query);
  const [projects, setProjects] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("all");

  useEffect(() => {
    setInput(query);
  }, [query]);

  // Return to the exact page that opened Search.
  function goBack() {
    const previousPage = location.state?.from;

    if (
      typeof previousPage === "string" &&
      previousPage.startsWith("/") &&
      !previousPage.startsWith("//") &&
      !previousPage.startsWith("/search")
    ) {
      navigate(previousPage);
      return;
    }

    // Supports normal browser navigation when state is unavailable.
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }

    // Fallback when Search was opened directly.
    navigate("/dashboard");
  }

  useEffect(() => {
    if (!query.trim()) {
      setProjects([]);
      setDocuments([]);
      setError("");
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();

    async function loadResults() {
      setLoading(true);
      setError("");

      try {
        const [projectResponse, documentResponse] = await Promise.all([
          apiFetch("/projects/", {
            method: "GET",
            headers: { Accept: "application/json" },
            signal: controller.signal,
          }),

          apiFetch(
            "/upload/documents?page=1&page_size=100&sort_by=created_at&order=desc",
            {
              method: "GET",
              headers: { Accept: "application/json" },
              signal: controller.signal,
            },
          ),
        ]);

        const [projectPayload, documentPayload] = await Promise.all([
          projectResponse.json().catch(() => ({})),
          documentResponse.json().catch(() => ({})),
        ]);

        if (!projectResponse.ok) {
          throw new Error(
            getErrorMessage(projectPayload, "Unable to load projects."),
          );
        }

        if (!documentResponse.ok) {
          throw new Error(
            getErrorMessage(documentPayload, "Unable to load documents."),
          );
        }

        if (controller.signal.aborted) return;

        setProjects(getArray(projectPayload, "projects"));
        setDocuments(getArray(documentPayload, "documents"));
      } catch (err) {
        if (err.name === "AbortError") return;

        setError(err.message || "Unable to search your workspace.");
        setProjects([]);
        setDocuments([]);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    loadResults();

    return () => controller.abort();
  }, [query]);

  const filteredProjects = useMemo(() => {
    const term = query.trim().toLowerCase();

    if (!term) return [];

    return projects.filter((project) =>
      [getProjectName(project), getProjectId(project), project?.description]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term)),
    );
  }, [projects, query]);

  const filteredDocuments = useMemo(() => {
    const term = query.trim().toLowerCase();

    if (!term) return [];

    return documents.filter((document) =>
      [
        getDocumentName(document),
        document?.description,
        document?.extension,
        document?.project_id,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term)),
    );
  }, [documents, query]);

  const totalResults = filteredProjects.length + filteredDocuments.length;

  function submitSearch(event) {
    event.preventDefault();

    const term = input.trim();

    if (!term) {
      setSearchParams({});
      return;
    }

    setSearchParams({ q: term });
    setActiveTab("all");
  }

  function openProject(project) {
    const id = getProjectId(project);

    if (!id) return;

    navigate(`/projects/${encodeURIComponent(id)}`, {
      state: {
        from: `${location.pathname}${location.search}`,
      },
    });
  }

  function openDocument() {
    // Change this if your document library uses a different route.
    navigate("/knowledge", {
      state: {
        from: `${location.pathname}${location.search}`,
      },
    });
  }

  return (
    <main className="global-search-page">
      <div className="global-search-topbar">
        <button type="button" className="global-search-back" onClick={goBack}>
          <ArrowLeft size={18} />
          <span>Back</span>
        </button>

        
      </div>

      <header className="global-search-header">
        <span className="global-search-eyebrow">CONTEXTAPI WORKSPACE</span>

        <h1>Search your workspace</h1>

        <p>Find projects and uploaded documents from one place.</p>

        <form className="global-search-form" onSubmit={submitSearch}>
          <SearchIcon size={20} aria-hidden="true" />

          <input
            type="search"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Search projects and documents..."
            aria-label="Search projects and documents"
          />

          {input && (
            <button
              type="button"
              className="global-search-clear"
              onClick={() => setInput("")}
              aria-label="Clear search"
            >
              <X size={18} />
            </button>
          )}

          <button type="submit" className="global-search-submit">
            Search
          </button>
        </form>
      </header>

      {!query.trim() ? (
        <section className="global-search-empty">
          <span className="global-search-empty-icon">
            <SearchIcon size={30} />
          </span>

          <h2>Start searching</h2>

          <p>
            Enter a project name or document filename to see matching results.
          </p>
        </section>
      ) : (
        <>
          <div className="global-search-summary">
            <span>
              Results for <strong>“{query}”</strong>
            </span>

            {!loading && !error && (
              <span className="global-search-count">
                {totalResults} result
                {totalResults === 1 ? "" : "s"}
              </span>
            )}
          </div>

          <nav
            className="global-search-tabs"
            aria-label="Filter search results"
          >
            {[
              { id: "all", label: "All", count: totalResults },
              {
                id: "projects",
                label: "Projects",
                count: filteredProjects.length,
              },
              {
                id: "documents",
                label: "Documents",
                count: filteredDocuments.length,
              },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={activeTab === tab.id ? "active" : ""}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
                <span>{tab.count}</span>
              </button>
            ))}
          </nav>

          {loading ? (
            <div className="global-search-state">
              <LoaderCircle className="global-search-spinner" size={28} />
              <p>Searching your workspace...</p>
            </div>
          ) : error ? (
            <div className="global-search-error" role="alert">
              <AlertCircle size={21} />

              <div>
                <strong>Search failed</strong>
                <p>{error}</p>
              </div>
            </div>
          ) : totalResults === 0 ? (
            <div className="global-search-empty">
              <span className="global-search-empty-icon">
                <SearchIcon size={30} />
              </span>

              <h2>No results found</h2>

              <p>Try another keyword or check the spelling.</p>
            </div>
          ) : (
            <div className="global-search-results">
              {(activeTab === "all" || activeTab === "projects") &&
                filteredProjects.length > 0 && (
                  <section className="global-search-section">
                    <div className="global-search-section-heading">
                      <FolderKanban size={19} />
                      <h2>Projects</h2>
                      <span>{filteredProjects.length}</span>
                    </div>

                    {filteredProjects.map((project, index) => (
                      <button
                        className="global-search-result"
                        key={getProjectId(project) || `project-${index}`}
                        type="button"
                        onClick={() => openProject(project)}
                      >
                        <span className="global-search-result-icon project">
                          <FolderKanban size={21} />
                        </span>

                        <span className="global-search-result-content">
                          <strong>{getProjectName(project)}</strong>
                          <small>{project?.description || "Project"}</small>
                        </span>

                        <ArrowRight size={18} />
                      </button>
                    ))}
                  </section>
                )}

              {(activeTab === "all" || activeTab === "documents") &&
                filteredDocuments.length > 0 && (
                  <section className="global-search-section">
                    <div className="global-search-section-heading">
                      <FileText size={19} />
                      <h2>Documents</h2>
                      <span>{filteredDocuments.length}</span>
                    </div>

                    {filteredDocuments.map((document, index) => (
                      <button
                        className="global-search-result"
                        key={getDocumentId(document) || `document-${index}`}
                        type="button"
                        onClick={openDocument}
                      >
                        <span className="global-search-result-icon document">
                          <FileText size={21} />
                        </span>

                        <span className="global-search-result-content">
                          <strong>{getDocumentName(document)}</strong>
                          <small>
                            {document?.extension
                              ? String(document.extension).toUpperCase()
                              : "Uploaded document"}
                          </small>
                        </span>

                        <ArrowRight size={18} />
                      </button>
                    ))}
                  </section>
                )}

              {activeTab === "projects" && filteredProjects.length === 0 && (
                <p className="global-search-no-tab-results">
                  No matching projects.
                </p>
              )}

              {activeTab === "documents" && filteredDocuments.length === 0 && (
                <p className="global-search-no-tab-results">
                  No matching documents.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </main>
  );
}
