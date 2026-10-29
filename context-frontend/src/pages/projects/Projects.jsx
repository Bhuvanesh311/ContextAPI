import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Projects.css";
import { apiFetch } from "../../services/api";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "/backend"
).replace(/\/$/, "");

function getProjectList(response) {
  if (Array.isArray(response)) return response;
  if (Array.isArray(response?.projects)) return response.projects;
  if (Array.isArray(response?.items)) return response.items;
  if (Array.isArray(response?.results)) return response.results;
  if (Array.isArray(response?.data)) return response.data;
  if (Array.isArray(response?.data?.projects)) return response.data.projects;
  return [];
}

function getProjectName(project) {
  return (
    project.name ||
    project.project_name ||
    project.title ||
    project.project_id ||
    "Untitled project"
  );
}

export default function Projects() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError("");

    const token = sessionStorage.getItem("inferai_access_token");

    if (!token) {
      setError("Your session has expired. Please log in again.");
      setLoading(false);
      return;
    }

    try {
      const response = await apiFetch("/projects/");

      if (response.status === 401 || response.status === 403) {
        throw new Error("You are not authorized to view these projects.");
      }

      if (!response.ok) {
        throw new Error(`Unable to load projects (HTTP ${response.status}).`);
      }

      const data = await response.json();
      setProjects(getProjectList(data));
    } catch (err) {
      setError(err.message || "Could not connect to the ContextAPI backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  return (
    <main className="infer-projects-page">
      <section className="projects-hero">
        <div className="projects-hero-content">
          <span className="projects-eyebrow">
            <span className="projects-status-dot" />
            CONTEXTAPI WORKSPACE
          </span>

          <h1>
            Your projects.
            <br />
            <span>Intelligence in motion.</span>
          </h1>

          <p>
            Organize your knowledge, documents, and AI-powered workflows in one
            intelligent workspace.
          </p>

          <div className="projects-hero-actions">
            <button
              className="projects-primary-button"
              onClick={() => navigate("/projects/create")}
              type="button"
            >
              <span>＋</span> Create Project
            </button>

            <button
              className="projects-secondary-button"
              onClick={loadProjects}
              disabled={loading}
              type="button"
            >
              ↻ Refresh
            </button>
          </div>
        </div>

        <div className="projects-hero-orbit" aria-hidden="true">
          <div className="projects-orbit-ring projects-orbit-ring-one" />
          <div className="projects-orbit-ring projects-orbit-ring-two" />
          <div className="projects-orbit-core">
            <span>AI</span>
          </div>
        </div>
      </section>

      <section className="projects-overview">
        <div className="projects-section-heading">
          <div>
            <span className="projects-eyebrow">YOUR WORKSPACE</span>
            <h2>Projects overview</h2>
            <p>Manage and explore your connected projects.</p>
          </div>

          <div className="projects-count-card">
            <span>Total projects</span>
            <strong>{loading ? "—" : projects.length}</strong>
          </div>
        </div>

        {loading ? (
          <div className="projects-state-card">
            <div className="projects-loader" />
            <h3>Loading your projects</h3>
            <p>Connecting to your ContextAPI workspace…</p>
          </div>
        ) : error ? (
          <div className="projects-state-card projects-error-state">
            <div className="projects-state-icon">!</div>
            <h3>Projects unavailable</h3>
            <p>{error}</p>
            <button
              className="projects-primary-button"
              onClick={loadProjects}
              type="button"
            >
              Try again
            </button>
          </div>
        ) : projects.length === 0 ? (
          <div className="projects-state-card">
            <div className="projects-state-icon">✧</div>
            <h3>Your workspace is ready</h3>
            <p>
              No projects were returned by the backend. Create your first
              project to get started.
            </p>
            <button
              className="projects-primary-button"
              onClick={() => navigate("/projects/create")}
              type="button"
            >
              ＋ Create your first project
            </button>
          </div>
        ) : (
          <div className="projects-grid">
            {projects.map((project, index) => (
              <article
                className="projects-card"
                key={
                  project.project_id ??
                  project.id ??
                  `${getProjectName(project)}-${index}`
                }
                role="link"
                tabIndex={0}
                onClick={() =>
                  navigate(
                    `/projects/${encodeURIComponent(
                      project.project_id ?? project.id,
                    )}`,
                  )
                }
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    navigate(
                      `/projects/${encodeURIComponent(
                        project.project_id ?? project.id,
                      )}`,
                    );
                  }
                }}
              >
                <div className="projects-card-top">
                  <div className="projects-card-icon">
                    {String(getProjectName(project)).charAt(0).toUpperCase()}
                  </div>
                  <span className="projects-card-index">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                </div>

                <h3>{getProjectName(project)}</h3>
                <p className="projects-card-description">
                  {project.description ||
                    project.summary ||
                    "Your AI-powered project workspace."}
                </p>

                <div className="projects-card-footer">
                  <span className="projects-card-status">
                    <span className="projects-status-dot" />
                    Connected project
                  </span>
                  <span aria-hidden="true">↗</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
