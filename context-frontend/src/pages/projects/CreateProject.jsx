import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import "./CreateProject.css";
import { apiFetch } from "../../services/api";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "/backend"
).replace(/\/$/, "");

export default function CreateProject() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("active");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const trimmedName = name.trim();

    if (trimmedName.length < 3 || trimmedName.length > 100) {
      setError("Project name must contain between 3 and 100 characters.");
      return;
    }

    if (description.length > 1000) {
      setError("Description cannot exceed 1,000 characters.");
      return;
    }

    setLoading(true);

    try {
      const response = await apiFetch("/projects/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          name: trimmedName,
          description: description.trim() || null,
          status,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = data.detail;
        const message =
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((item) => item.msg).join(", ")
              : data.message || `Project creation failed (${response.status}).`;

        throw new Error(message);
      }

      setSuccess(data.message || "Project created successfully.");

      // Allow the success message to be seen before opening the list.
      window.setTimeout(() => navigate("/projects"), 700);
    } catch (err) {
      setError(err.message || "Unable to connect to the backend.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="infer-create-project-page">
      <div className="create-project-breadcrumb">
        <button
          type="button"
          className="project-back-button"
          onClick={() => navigate(-1)}
          aria-label="Go back"
          title="Go back"
        >
          <ArrowLeft size={20} />
        </button>

        <span > Projects</span>
      </div>

      <section className="create-project-layout">
        <div className="create-project-intro">
          <span className="create-project-eyebrow">
            <span className="create-project-dot" />
            CONTEXTAPI WORKSPACE
          </span>

          <h1>
            Start something
            <br />
            <span>intelligent.</span>
          </h1>

          <p>
            Create a dedicated workspace for your documents, knowledge, and
            AI-powered retrieval workflows.
          </p>

          <div className="create-project-feature">
            <span>01</span>
            <div>
              <strong>Organize knowledge</strong>
              <p>Keep project information in one place.</p>
            </div>
          </div>

          <div className="create-project-feature">
            <span>02</span>
            <div>
              <strong>Enable AI retrieval</strong>
              <p>Use an active project for retrieval workflows.</p>
            </div>
          </div>
        </div>

        <form className="create-project-form" onSubmit={handleSubmit}>
          <div className="create-project-form-heading">
            <span className="create-project-form-icon">✦</span>
            <div>
              <h2>Create a project</h2>
              <p>Enter the details for your new workspace.</p>
            </div>
          </div>

          {error && (
            <div
              className="create-project-message create-project-error"
              role="alert"
            >
              {error}
            </div>
          )}

          {success && (
            <div
              className="create-project-message create-project-success"
              role="status"
            >
              {success}
            </div>
          )}

          <label htmlFor="project-name">Project name *</label>
          <input
            id="project-name"
            name="name"
            type="text"
            placeholder="e.g. Company Knowledge Base"
            value={name}
            onChange={(event) => setName(event.target.value)}
            minLength={3}
            maxLength={100}
            required
            autoFocus
          />
          <div className="create-project-field-hint">
            {name.length}/100 characters
          </div>

          <label htmlFor="project-description">Description</label>
          <textarea
            id="project-description"
            name="description"
            placeholder="Describe what this project will be used for..."
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={1000}
            rows={5}
          />
          <div className="create-project-field-hint">
            {description.length}/1000 characters
          </div>

          <label htmlFor="project-status">Initial status</label>
          <select
            id="project-status"
            name="status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="active">Active — ready for retrieval</option>
            <option value="pending">Pending — not yet active</option>
          </select>

          <div className="create-project-form-actions">
            <button
              type="button"
              className="create-project-cancel"
              onClick={() => navigate("/projects")}
              disabled={loading}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="create-project-submit"
              disabled={loading}
            >
              {loading ? "Creating..." : "＋ Create Project"}
            </button>
          </div>

          <p className="create-project-secure-note">
            Your project is created through the authenticated ContextAPI backend.
          </p>
        </form>
      </section>
    </main>
  );
}
