import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AppWindow,
  Plus,
  Search,
  RefreshCw,
  ExternalLink,
  Pencil,
  Trash2,
  X,
  Globe,
  FolderKanban,
  CheckCircle2,
  AlertCircle,
  Layers3,
  LoaderCircle,
  ChevronDown,
} from "lucide-react";
import { apiFetch } from "../../services/api";
import "./TargetApplications.css";

const PROJECTS_URL = "/projects/";
const STORAGE_KEY = "inferai_target_applications_session";

const collectionUrl = (projectId) =>
  `/projects/${encodeURIComponent(projectId)}/target-applications/`;

const detailUrl = (projectId, targetId) =>
  `${collectionUrl(projectId)}${encodeURIComponent(targetId)}`;

const emptyForm = {
  project_id: "",
  base_url: "",
  environment: "",
  api_version: "",
};

async function requestJson(url, options = {}) {
  const response = await apiFetch(url, options);

  if (response && typeof response.json === "function") {
    const data =
      response.status === 204 ? null : await response.json().catch(() => null);

    if (!response.ok) {
      const detail = data?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail
                .map((item) =>
                  typeof item === "string"
                    ? item
                    : `${item.loc?.join(".") ?? "field"}: ${item.msg}`,
                )
                .join("; ")
            : data?.message;

      throw new Error(message || `Request failed (${response.status})`);
    }

    return data;
  }

  return response;
}

function getArray(payload, key) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.[key])) return payload[key];
  if (Array.isArray(payload?.data?.[key])) return payload.data[key];
  if (Array.isArray(payload?.data)) return payload.data;
  return [];
}

function getProjectId(project) {
  return String(project?.project_id ?? project?.id ?? "");
}

function getProjectName(project) {
  return (
    project?.project_name ??
    project?.name ??
    project?.projectName ??
    project?.title ??
    "Unnamed project"
  );
}

function getTargetId(target) {
  return String(target?.target_application_id ?? "");
}

function getTargetFromResponse(payload) {
  return (
    payload?.target_application ??
    payload?.data?.target_application ??
    payload?.data ??
    payload
  );
}

function environmentLabel(value) {
  if (!value) return "Unknown";
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

function readSessionTargets() {
  try {
    const value = sessionStorage.getItem(STORAGE_KEY);
    const parsed = value ? JSON.parse(value) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveSessionTargets(targets) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(targets));
  } catch {
    // The page remains usable if session storage is unavailable.
  }
}

export default function TargetApplications() {
  const [projects, setProjects] = useState([]);
  const [applications, setApplications] = useState(readSessionTargets);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pageError, setPageError] = useState("");
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [environmentFilter, setEnvironmentFilter] = useState("all");

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);

  const [projectSearch, setProjectSearch] = useState("");
  const [projectDropdownOpen, setProjectDropdownOpen] = useState(false);
  const [deleteCandidate, setDeleteCandidate] = useState(null);

  const loadProjects = useCallback(async () => {
    setLoadingProjects(true);
    setPageError("");

    try {
      const payload = await requestJson(PROJECTS_URL);
      setProjects(getArray(payload, "projects"));
    } catch (error) {
      setPageError(error?.message || "Could not load projects.");
    } finally {
      setLoadingProjects(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    saveSessionTargets(applications);
  }, [applications]);

  const filteredProjects = useMemo(() => {
    const term = projectSearch.trim().toLowerCase();

    return projects.filter((project) => {
      if (!term) return true;

      return (
        getProjectName(project).toLowerCase().includes(term) ||
        getProjectId(project).toLowerCase().includes(term)
      );
    });
  }, [projects, projectSearch]);

  const filteredApplications = useMemo(() => {
    const term = search.trim().toLowerCase();

    return applications.filter((target) => {
      const searchable = [
        target.base_url,
        target.environment,
        target.api_version,
        target.target_application_id,
        target.project_id,
        target.project_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return (
        (!term || searchable.includes(term)) &&
        (environmentFilter === "all" ||
          String(target.environment).toLowerCase() === environmentFilter)
      );
    });
  }, [applications, search, environmentFilter]);

  const environments = [
    "development",
    "testing",
    "staging",
    "production",
    "sandbox",
  ];

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setProjectSearch("");
    setProjectDropdownOpen(false);
    setFormError("");
    setModalOpen(true);
  };

  const openEdit = (target) => {
    setEditing(target);
    setForm({
      project_id: String(target.project_id ?? ""),
      base_url: target.base_url ?? "",
      environment: String(target.environment ?? "").toLowerCase(),
      api_version: target.api_version ?? "",
    });

    const project = projects.find(
      (item) => getProjectId(item) === String(target.project_id),
    );

    setProjectSearch(project ? getProjectName(project) : "Unnamed project");

    setProjectDropdownOpen(false);
    setFormError("");
    setModalOpen(true);
  };

  const closeModal = () => {
    if (saving) return;
    setModalOpen(false);
    setEditing(null);
    setForm(emptyForm);
    setProjectSearch("");
    setProjectDropdownOpen(false);
    setFormError("");
  };

  const selectProject = (project) => {
    setForm((current) => ({
      ...current,
      project_id: getProjectId(project),
    }));

    setProjectSearch(getProjectName(project));

    setProjectDropdownOpen(false);
  };

  const updateField = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  };

  const saveTarget = async (event) => {
    event.preventDefault();
    setFormError("");
    setNotice("");

    if (!form.project_id) {
      setFormError("Select a project from the project search results.");
      return;
    }

    if (!form.base_url.trim()) {
      setFormError("Base URL is required.");
      return;
    }

    try {
      const parsedUrl = new URL(form.base_url.trim());

      if (!["http:", "https:"].includes(parsedUrl.protocol)) {
        throw new Error("Unsupported URL scheme");
      }
    } catch {
      setFormError("Enter a valid URL starting with https:// or http://.");
      return;
    }

    if (!form.environment) {
      setFormError("Select an environment.");
      return;
    }

    const createBody = {
      project_id: form.project_id,
      base_url: form.base_url.trim(),
      environment: form.environment,
      api_version: form.api_version.trim() || null,
    };

    const updateBody = {
      base_url: form.base_url.trim(),
      environment: form.environment,
      api_version: form.api_version.trim() || null,
    };

    setSaving(true);

    try {
      if (editing) {
        const targetId = getTargetId(editing);

        if (!targetId) {
          throw new Error(
            "This target has no target_application_id, so it cannot be updated.",
          );
        }

        const payload = await requestJson(
          detailUrl(editing.project_id, targetId),
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(updateBody),
          },
        );

        const saved = getTargetFromResponse(payload);

        setApplications((current) =>
          current.map((item) =>
            getTargetId(item) === targetId &&
            String(item.project_id) === String(editing.project_id)
              ? {
                  ...item,
                  ...(saved ?? {}),
                  ...updateBody,
                  project_id: editing.project_id,
                  project_name: editing.project_name,
                }
              : item,
          ),
        );

        setNotice("Target application updated successfully.");
      } else {
        const payload = await requestJson(collectionUrl(form.project_id), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(createBody),
        });

        const saved = getTargetFromResponse(payload);

        if (!saved || typeof saved !== "object") {
          throw new Error("The server did not return the created target.");
        }

        const project = projects.find(
          (item) => getProjectId(item) === form.project_id,
        );

        const target = {
          ...saved,
          ...createBody,
          project_id: form.project_id,
          project_name: project ? getProjectName(project) : form.project_id,
        };

        setApplications((current) => [
          target,
          ...current.filter(
            (item) =>
              !getTargetId(target) ||
              getTargetId(item) !== getTargetId(target) ||
              String(item.project_id) !== String(target.project_id),
          ),
        ]);

        setNotice(
          "Target created. It is shown in this browser session because the backend has no list endpoint.",
        );
      }

      setModalOpen(false);
      setEditing(null);
      setForm(emptyForm);
      setProjectSearch("");
    } catch (error) {
      setFormError(error?.message || "Could not save the target application.");
    } finally {
      setSaving(false);
    }
  };

  const deleteTarget = async () => {
    if (!deleteCandidate) return;

    const projectId = String(deleteCandidate.project_id ?? "");
    const targetId = getTargetId(deleteCandidate);

    if (!projectId || !targetId) {
      setPageError("The project ID or target application ID is missing.");
      setDeleteCandidate(null);
      return;
    }

    try {
      setPageError("");

      await requestJson(detailUrl(projectId, targetId), {
        method: "DELETE",
      });

      setApplications((current) =>
        current.filter(
          (item) =>
            !(
              getTargetId(item) === targetId &&
              String(item.project_id) === projectId
            ),
        ),
      );

      setNotice("Target application deleted successfully.");
    } catch (error) {
      setPageError(error?.message || "Could not delete the target.");
    } finally {
      setDeleteCandidate(null);
    }
  };

  return (
    <main className="ta-page">
      <div className="ta-page-inner">
        <header className="ta-heading">
          <div className="ta-heading-copy">
            <div className="ta-eyebrow">
              <Layers3 size={14} />
              CONTEXTAPI / INTEGRATIONS
            </div>
            <h1>Target Applications</h1>
            <p>Manage target endpoints associated with your projects.</p>
          </div>

          <div className="ta-heading-actions">
            <button
              type="button"
              className="ta-button ta-button-secondary"
              onClick={loadProjects}
              disabled={loadingProjects}
            >
              <RefreshCw
                size={16}
                className={loadingProjects ? "ta-spin" : ""}
              />
              Refresh projects
            </button>

            <button
              type="button"
              className="ta-button ta-button-primary"
              onClick={openCreate}
            >
              <Plus size={17} />
              Add Target
            </button>
          </div>
        </header>

        {notice && (
          <div className="ta-alert ta-alert-success">
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

        {pageError && (
          <div className="ta-alert ta-alert-error">
            <AlertCircle size={17} />
            <span>{pageError}</span>
            <button
              type="button"
              onClick={() => setPageError("")}
              aria-label="Dismiss"
            >
              <X size={16} />
            </button>
          </div>
        )}

        <section className="ta-stats">
          <article className="ta-stat-card">
            <span className="ta-stat-icon">
              <AppWindow size={20} />
            </span>
            <div>
              <span className="ta-stat-label">Known targets</span>
              <strong>{applications.length}</strong>
              <small>Targets available in this browser session</small>
            </div>
          </article>

          <article className="ta-stat-card">
            <span className="ta-stat-icon ta-stat-icon-green">
              <Globe size={20} />
            </span>
            <div>
              <span className="ta-stat-label">Configured endpoints</span>
              <strong>
                {applications.filter((item) => item.base_url).length}
              </strong>
              <small>Saved in the current session list</small>
            </div>
          </article>

          <article className="ta-stat-card">
            <span className="ta-stat-icon ta-stat-icon-purple">
              <FolderKanban size={20} />
            </span>
            <div>
              <span className="ta-stat-label">Available projects</span>
              <strong>{projects.length}</strong>
              <small>Projects returned by the backend</small>
            </div>
          </article>
        </section>

        <section className="ta-content-panel">
          <div className="ta-list-heading">
            <div>
              <h2>Your integrations</h2>
              <p>
                Search the targets created or loaded in this browser session.
              </p>
            </div>
            <span className="ta-count-pill">
              {filteredApplications.length} shown
            </span>
          </div>

          <div className="ta-toolbar">
            <label className="ta-search-box">
              <Search size={18} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search URL, environment, or project..."
                aria-label="Search target applications"
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

            <div className="ta-status-filter">
              <button
                type="button"
                className={environmentFilter === "all" ? "selected" : ""}
                onClick={() => setEnvironmentFilter("all")}
              >
                All
              </button>
              {environments.map((environment) => (
                <button
                  type="button"
                  key={environment}
                  className={
                    environmentFilter === environment ? "selected" : ""
                  }
                  onClick={() => setEnvironmentFilter(environment)}
                >
                  {environmentLabel(environment)}
                </button>
              ))}
            </div>
          </div>

          {loadingProjects ? (
            <div className="ta-state">
              <LoaderCircle size={28} className="ta-spin" />
              <strong>Loading projects</strong>
              <span>Retrieving your available projects...</span>
            </div>
          ) : filteredApplications.length === 0 ? (
            <div className="ta-state">
              <span className="ta-empty-icon">
                <AppWindow size={28} />
              </span>
              <strong>
                {applications.length
                  ? "No matching targets"
                  : "No targets loaded in this session"}
              </strong>
              <span>
                {applications.length
                  ? "Try a different search or environment filter."
                  : "Your backend does not expose a target-list endpoint. Add a target to show it here."}
              </span>
              {!applications.length && (
                <button
                  type="button"
                  className="ta-button ta-button-primary"
                  onClick={openCreate}
                >
                  <Plus size={16} />
                  Add your first target
                </button>
              )}
            </div>
          ) : (
            <div className="ta-application-grid">
              {filteredApplications.map((target, index) => (
                <article
                  className="ta-application-card"
                  key={`${target.project_id}-${getTargetId(target) || target.base_url || index}`}
                >
                  <div className="ta-card-top">
                    <div className="ta-app-symbol">
                      <AppWindow size={22} />
                    </div>
                    <span className="ta-status-badge is-active">
                      <span />
                      {environmentLabel(target.environment)}
                    </span>
                  </div>

                  <h3>{target.base_url}</h3>
                  <p className="ta-app-type">
                    {target.api_version
                      ? `API ${target.api_version}`
                      : "Target endpoint"}
                  </p>

                  <div className="ta-app-url">
                    <Globe size={15} />
                    <a href={target.base_url} target="_blank" rel="noreferrer">
                      Open endpoint <ExternalLink size={12} />
                    </a>
                  </div>

                  <div className="ta-project-chip">
                    <FolderKanban size={14} />
                    <span>{target.project_name || "Project"}</span>
                  </div>

                  <div className="ta-card-footer">
                    <span>ID: {getTargetId(target) || "Not returned"}</span>
                    <div>
                      <button
                        type="button"
                        title="Refresh target details"
                        aria-label="Refresh target details"
                        disabled={!getTargetId(target)}
                        onClick={async () => {
                          try {
                            const payload = await requestJson(
                              detailUrl(target.project_id, getTargetId(target)),
                            );
                            const saved = getTargetFromResponse(payload);

                            setApplications((current) =>
                              current.map((item) =>
                                getTargetId(item) === getTargetId(target) &&
                                String(item.project_id) ===
                                  String(target.project_id)
                                  ? {
                                      ...item,
                                      ...saved,
                                      project_name: target.project_name,
                                    }
                                  : item,
                              ),
                            );
                            setNotice("Target details refreshed.");
                          } catch (error) {
                            setPageError(
                              error?.message ||
                                "Could not load target details.",
                            );
                          }
                        }}
                      >
                        <RefreshCw size={16} />
                      </button>

                      <button
                        type="button"
                        title="Edit target"
                        aria-label="Edit target"
                        onClick={() => openEdit(target)}
                      >
                        <Pencil size={16} />
                      </button>

                      <button
                        type="button"
                        className="ta-delete-action"
                        title="Delete target"
                        aria-label="Delete target"
                        onClick={() => setDeleteCandidate(target)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      {modalOpen && (
        <div
          className="ta-modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeModal();
          }}
        >
          <section
            className="ta-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="ta-modal-title"
          >
            <header className="ta-modal-header">
              <div className="ta-modal-heading-icon">
                {editing ? <Pencil size={21} /> : <Plus size={22} />}
              </div>
              <div>
                <h2 id="ta-modal-title">
                  {editing
                    ? "Edit target application"
                    : "Add target application"}
                </h2>
                <p>Select a project and configure its target endpoint.</p>
              </div>
              <button
                type="button"
                className="ta-modal-close"
                onClick={closeModal}
                disabled={saving}
                aria-label="Close form"
              >
                <X size={20} />
              </button>
            </header>

            <form className="ta-form" onSubmit={saveTarget}>
              {formError && (
                <div className="ta-alert ta-alert-error">
                  <AlertCircle size={17} />
                  <span>{formError}</span>
                </div>
              )}

              <div className="ta-field">
                <label htmlFor="ta-project-search">
                  Project <span>*</span>
                </label>
                <div className="ta-project-picker">
                  <div className="ta-project-search-input">
                    <Search size={17} />
                    <input
                      id="ta-project-search"
                      value={projectSearch}
                      onChange={(event) => {
                        setProjectSearch(event.target.value);
                        setProjectDropdownOpen(true);
                        setForm((current) => ({ ...current, project_id: "" }));
                      }}
                      onFocus={() => setProjectDropdownOpen(true)}
                      placeholder="Search project name or ID..."
                      autoComplete="off"
                      aria-expanded={projectDropdownOpen}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setProjectSearch("");
                        setForm((current) => ({ ...current, project_id: "" }));
                        setProjectDropdownOpen(true);
                      }}
                      aria-label="Clear project selection"
                    >
                      {form.project_id ? (
                        <X size={15} />
                      ) : (
                        <ChevronDown size={17} />
                      )}
                    </button>
                  </div>

                  {projectDropdownOpen && (
                    <div className="ta-project-options">
                      {filteredProjects.length === 0 ? (
                        <div className="ta-project-option-empty">
                          {loadingProjects
                            ? "Loading projects..."
                            : "No matching projects."}
                        </div>
                      ) : (
                        filteredProjects.map((project) => (
                          <button
                            type="button"
                            key={getProjectId(project)}
                            className={
                              form.project_id === getProjectId(project)
                                ? "ta-project-option selected"
                                : "ta-project-option"
                            }
                            onClick={() => selectProject(project)}
                          >
                            <span className="ta-project-option-icon">
                              <FolderKanban size={17} />
                            </span>
                            <span className="ta-project-option-copy">
                              <strong>{getProjectName(project)}</strong>
                              {/* <small>{getProjectId(project)}</small> */}
                            </span>
                            {form.project_id === getProjectId(project) && (
                              <CheckCircle2 size={17} />
                            )}
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>

                {/* {form.project_id && (
                  <small className="ta-field-help">
                    Selected project ID: <code>{form.project_id}</code>
                  </small>
                )} */}
              </div>

              <div className="ta-field">
                <label htmlFor="ta-base-url">
                  Base URL <span>*</span>
                </label>
                <input
                  id="ta-base-url"
                  name="base_url"
                  type="url"
                  value={form.base_url}
                  onChange={updateField}
                  placeholder="https://example.com"
                  maxLength={500}
                  required
                />
              </div>

              <div className="ta-field">
                <label htmlFor="ta-environment">
                  Environment <span>*</span>
                </label>
                <select
                  id="ta-environment"
                  name="environment"
                  value={form.environment}
                  onChange={updateField}
                  required
                >
                  <option value="">Select environment</option>
                  {environments.map((environment) => (
                    <option key={environment} value={environment}>
                      {environmentLabel(environment)}
                    </option>
                  ))}
                </select>
              </div>

              <div className="ta-field">
                <label htmlFor="ta-api-version">API version</label>
                <input
                  id="ta-api-version"
                  name="api_version"
                  value={form.api_version}
                  onChange={updateField}
                  placeholder="e.g. v1"
                  maxLength={50}
                />
              </div>

              <footer className="ta-form-footer">
                <button
                  type="button"
                  className="ta-button ta-button-secondary"
                  onClick={closeModal}
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="ta-button ta-button-primary"
                  disabled={saving}
                >
                  {saving ? (
                    <>
                      <LoaderCircle size={16} className="ta-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      {editing ? <Pencil size={16} /> : <Plus size={17} />}
                      {editing ? "Save changes" : "Create target"}
                    </>
                  )}
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}

      {deleteCandidate && (
        <div className="ta-modal-backdrop">
          <section
            className="ta-confirm-modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="ta-delete-title"
          >
            <span className="ta-confirm-icon">
              <Trash2 size={23} />
            </span>
            <h2 id="ta-delete-title">Delete target application?</h2>
            <p>
              Delete <strong>{deleteCandidate.base_url}</strong>? This action
              cannot be undone.
            </p>
            <div className="ta-form-footer">
              <button
                type="button"
                className="ta-button ta-button-secondary"
                onClick={() => setDeleteCandidate(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="ta-button ta-button-danger"
                onClick={deleteTarget}
              >
                <Trash2 size={16} />
                Delete
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
