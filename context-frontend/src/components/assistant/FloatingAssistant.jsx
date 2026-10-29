import { useEffect, useRef, useState } from "react";
import {
  Bot,
  X,
  Send,
  Sparkles,
  Paperclip,
  FileArchive,
  FileText,
  Search,
  LoaderCircle,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  RotateCcw,
  Square,
} from "lucide-react";
import { apiFetch } from "../../services/api";
import {
  askQuestion,
  cancelRequest,
  getAnswer,
  isTransient,
  RequestError,
  shortId,
} from "../../services/retrieval";
import { stopDocument } from "../../services/documents";
import {
  describeUploadOutcome,
  UPLOAD_ACCEPT,
  uploadFiles,
  uploadPercent,
} from "../../services/uploads";
import AssistantTurn from "./AssistantTurn";
import { MODES } from "./modes";
import "./FloatingAssistant.css";

const MAX_POLL_RETRIES = 6;
const DOCUMENT_POLL_MS = 3000;
// Stop watching an upload that never shows up in the document list.
const DOCUMENT_WATCH_MS = 10 * 60 * 1000;

const PENDING_STATUSES = ["UPLOADING", "PENDING", "QUEUED", "PROCESSING", "INDEXING", "INGESTING"];
const READY_STATUSES = ["READY", "COMPLETED", "INDEXED", "SUCCESS"];
const FAILED_STATUSES = ["FAILED", "ERROR", "REJECTED", "CANCELLED"];

const SUGGESTIONS = [
  "Summarize these documents",
  "What are the key points?",
  "List the main requirements",
];

async function readResponse(response) {
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : detail?.message || data?.message || "Request failed.",
    );
  }

  return data?.data ?? data;
}

function getProjects(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.projects)) return data.projects;
  if (Array.isArray(data?.items)) return data.items;
  return [];
}

function normalizeStatus(item) {
  return String(
    item?.indexing_status || item?.status || "UPLOADED",
  ).toUpperCase();
}

function statusText(status) {
  if (READY_STATUSES.includes(status)) return "Ready";
  if (status === "CANCELLED") return "Stopped";
  if (FAILED_STATUSES.includes(status)) return "Failed";
  if (status === "UPLOADING") return "Uploading";
  if (PENDING_STATUSES.includes(status)) return "Processing";
  return "Uploaded";
}

function isZipFile(name) {
  return name.toLowerCase().endsWith(".zip");
}

// The API sends UTC timestamps without a zone; plain Date() would read them
// as local time.
function parseServerDate(iso) {
  if (!iso) return 0;
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

// ---------- chat persistence (per project, in this browser) ----------

const chatKey = (projectId) => `inferai.assistant.v1.${projectId}`;

function loadChat(projectId) {
  const fresh = { projectId, conversationId: shortId("c"), turns: [] };
  if (!projectId) return fresh;

  try {
    const raw = localStorage.getItem(chatKey(projectId));
    if (raw) {
      const saved = JSON.parse(raw);
      return { projectId, conversationId: saved.conversationId, turns: saved.turns ?? [] };
    }
  } catch {
    // Unreadable storage: start fresh.
  }

  return fresh;
}

function saveChat(chat) {
  if (!chat.projectId) return;

  try {
    localStorage.setItem(
      chatKey(chat.projectId),
      JSON.stringify({ conversationId: chat.conversationId, turns: chat.turns.slice(-60) }),
    );
  } catch {
    // Storage full or blocked: the chat still works, it just won't survive a reload.
  }
}

export default function FloatingAssistant() {
  const [isOpen, setIsOpen] = useState(false);

  // Keep the original ball movement settings.
  const [position, setPosition] = useState({
    x: typeof window !== "undefined" ? window.innerWidth - 90 : 900,
    y: typeof window !== "undefined" ? window.innerHeight - 100 : 700,
  });

  const [message, setMessage] = useState("");
  const [mode, setMode] = useState("DEEP");
  const [chat, setChat] = useState(() => loadChat(""));

  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [projectSearch, setProjectSearch] = useState("");
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(false);

  const [uploads, setUploads] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [error, setError] = useState("");

  const dragRef = useRef(null);
  const conversationRef = useRef(null);
  const fileInputRef = useRef(null);
  const projectSelectRef = useRef(null);
  const controllers = useRef(new Map());
  const uploadWatch = useRef(null);
  const stickToBottom = useRef(true);

  const turns = chat.turns;
  const sending = turns.some((turn) => turn.pending);

  const selectedProject = projects.find(
    (project) => String(project.project_id ?? project.id ?? "") === projectId,
  );

  const filteredProjects = projects.filter((project) => {
    const name = String(
      project.name ?? project.project_name ?? project.project_id ?? "",
    );
    return name.toLowerCase().includes(projectSearch.trim().toLowerCase());
  });

  useEffect(() => saveChat(chat), [chat]);

  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;

    async function loadProjects() {
      setLoadingProjects(true);
      setError("");

      try {
        const response = await apiFetch("/projects/", {
          headers: { Accept: "application/json" },
        });
        const data = await readResponse(response);
        const list = getProjects(data);

        if (cancelled) return;

        setProjects(list);

        setProjectId((previous) => {
          if (
            previous &&
            list.some(
              (project) =>
                String(project.project_id ?? project.id ?? "") === previous,
            )
          ) {
            return previous;
          }

          return "";
        });
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "Unable to load projects.");
        }
      } finally {
        if (!cancelled) setLoadingProjects(false);
      }
    }

    loadProjects();

    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  // Switching project opens that project's conversation and resumes any
  // question that was still running when it was left (or the page closed).
  useEffect(() => {
    const map = controllers.current;
    const next = loadChat(projectId);
    setChat(next);
    setUploads([]);
    stickToBottom.current = true;

    for (const turn of next.turns) {
      if (!turn.pending) continue;
      if (turn.requestId) poll(turn, turn.requestId);
      else update(turn.id, { pending: false, error: "Interrupted before it was sent." });
    }

    return () => {
      map.forEach((controller) => controller.abort());
      map.clear();
      uploadWatch.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Follow the conversation unless the reader scrolled up.
  useEffect(() => {
    const el = conversationRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  });

  useEffect(() => {
    function handleOutsideClick(event) {
      if (
        projectSelectRef.current &&
        !projectSelectRef.current.contains(event.target)
      ) {
        setProjectMenuOpen(false);
      }
    }

    document.addEventListener("pointerdown", handleOutsideClick);

    return () => {
      document.removeEventListener("pointerdown", handleOutsideClick);
    };
  }, []);

  // Original drag behavior preserved.
  function handlePointerDown(event) {
    if (event.button !== 0) return;

    event.currentTarget.setPointerCapture(event.pointerId);

    dragRef.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      startX: position.x,
      startY: position.y,
      moved: false,
    };
  }

  function handlePointerMove(event) {
    if (!dragRef.current) return;

    const drag = dragRef.current;
    const dx = event.clientX - drag.pointerX;
    const dy = event.clientY - drag.pointerY;

    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
      drag.moved = true;
    }

    if (!drag.moved) return;

    setPosition({
      x: Math.max(36, Math.min(window.innerWidth - 36, drag.startX + dx)),
      y: Math.max(36, Math.min(window.innerHeight - 36, drag.startY + dy)),
    });
  }

  function handlePointerUp() {
    if (!dragRef.current) return;

    const moved = dragRef.current.moved;
    dragRef.current = null;

    if (!moved) {
      setError("");
      setIsOpen((previous) => !previous);
    }
  }

  function selectProject(project) {
    const id = String(project.project_id ?? project.id ?? "");
    setProjectId(id);
    setProjectSearch(
      String(project.name ?? project.project_name ?? project.project_id ?? ""),
    );
    setProjectMenuOpen(false);
    setError("");
  }

  // ---------- questions ----------

  function update(turnId, patch) {
    setChat((previous) => ({
      ...previous,
      turns: previous.turns.map((turn) =>
        turn.id === turnId ? { ...turn, ...patch } : turn,
      ),
    }));
  }

  async function poll(turn, requestId) {
    const controller = new AbortController();
    controllers.current.set(turn.id, controller);
    // The request keeps running on the server, so a dropped connection or a
    // gateway hiccup is retried instead of failing the turn.
    let failures = 0;

    try {
      for (;;) {
        try {
          // Short waits so the answer appears while it is being written.
          const answer = await getAnswer(requestId, 1, controller.signal);
          failures = 0;

          if (answer.done) {
            update(turn.id, {
              answer,
              pending: false,
              stage: null,
              partial: null,
              elapsedMs: Date.now() - turn.startedAt,
            });
            return;
          }

          update(turn.id, { stage: answer.stage, partial: answer.partial_answer });
        } catch (err) {
          if (err.name === "AbortError") throw err;
          if (!isTransient(err) || ++failures > MAX_POLL_RETRIES) throw err;
          await sleep(Math.min(1000 * 2 ** (failures - 1), 8000), controller.signal);
        }
      }
    } catch (err) {
      if (err.name === "AbortError") return;
      update(turn.id, {
        error:
          err instanceof RequestError && err.status !== 0
            ? err.message
            : "Lost connection while waiting for the answer.",
        pending: false,
      });
    } finally {
      controllers.current.delete(turn.id);
    }
  }

  async function ask(text) {
    const question = text.trim();

    if (!question) return;

    if (!projectId) {
      setError("Select a project before asking a question.");
      return;
    }

    setError("");
    setMessage("");
    stickToBottom.current = true;

    const key = shortId("q");
    const turn = {
      id: key,
      question,
      profile: mode,
      pending: true,
      startedAt: Date.now(),
    };
    const conversationId = chat.conversationId;

    setChat((previous) => ({ ...previous, turns: [...previous.turns, turn] }));

    // The idempotency key lets a retried POST return the same request.
    for (let attempt = 0; ; attempt += 1) {
      try {
        const created = await askQuestion({
          projectId,
          question,
          profile: mode,
          conversationId,
          idempotencyKey: key,
        });

        update(turn.id, { requestId: created.request_id });
        await poll(turn, created.request_id);
        return;
      } catch (err) {
        if (attempt < 2 && isTransient(err)) {
          await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
          continue;
        }
        update(turn.id, {
          error: err.message || "Could not send the question.",
          pending: false,
        });
        return;
      }
    }
  }

  function handleSend(event) {
    event.preventDefault();
    ask(message);
  }

  function retry(turn) {
    if (!turn.requestId) return;
    update(turn.id, { pending: true, error: undefined });
    poll({ ...turn, pending: true, error: undefined }, turn.requestId);
  }

  async function cancel(turn) {
    controllers.current.get(turn.id)?.abort();
    update(turn.id, { pending: false, error: "Stopped.", cancelled: true, partial: null });

    if (turn.requestId) {
      try {
        await cancelRequest(turn.requestId);
      } catch {
        // Already finished or gone; nothing to undo.
      }
    }
  }

  function newConversation() {
    if (sending || !turns.length) return;
    if (!window.confirm("Start a new conversation? The documents stay in the project.")) return;

    // A fresh conversation id so earlier questions stop being used as context.
    setChat({ projectId, conversationId: shortId("c"), turns: [] });
    setUploads([]);
  }

  // ---------- uploads ----------

  // The upload response has no document ids, so new documents are matched by
  // file name among the project's documents created since the upload started.
  async function watchUploads(projectForUpload, items, since) {
    uploadWatch.current?.abort();
    const controller = new AbortController();
    uploadWatch.current = controller;
    const deadline = Date.now() + DOCUMENT_WATCH_MS;
    const open = new Map(items.map((item) => [item.key, item.name]));

    try {
      while (open.size && Date.now() < deadline) {
        await sleep(DOCUMENT_POLL_MS, controller.signal);

        const params = new URLSearchParams({
          project_id: projectForUpload,
          page: "1",
          page_size: "100",
          sort_by: "created_at",
          order: "desc",
        });

        let documents;
        try {
          const response = await apiFetch(`/upload/documents?${params}`, {
            headers: { Accept: "application/json" },
            signal: controller.signal,
          });
          const data = await readResponse(response);
          documents = Array.isArray(data?.documents) ? data.documents : [];
        } catch (err) {
          if (err.name === "AbortError") throw err;
          continue;
        }

        const changes = new Map();
        for (const [key, name] of open) {
          const document = documents.find(
            (doc) =>
              doc.original_filename === name &&
              parseServerDate(doc.created_at) >= since - 60_000,
          );
          if (!document) continue;

          const status = normalizeStatus(document);
          changes.set(key, { status, documentId: document.document_id });
          if (!PENDING_STATUSES.includes(status)) open.delete(key);
        }

        if (changes.size) {
          setUploads((previous) =>
            previous.map((item) => {
              const change = changes.get(item.key);
              return change
                ? { ...item, ...change, label: statusText(change.status) }
                : item;
            }),
          );
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") throw err;
    }
  }

  async function addFiles(files) {
    if (!files.length) return;

    if (!projectId) {
      setError("Search for and select a project before uploading.");
      return;
    }

    const projectForUpload = projectId;
    const since = Date.now();
    const newItems = files.map((file, index) => ({
      key: `${since}-${index}-${file.name}`,
      name: file.name,
      size: file.size,
      isZip: isZipFile(file.name),
      status: "UPLOADING",
      label: "Uploading",
    }));

    stickToBottom.current = true;
    setUploads((previous) => [...previous, ...newItems]);
    setUploading(true);
    setUploadProgress(null);
    setError("");

    try {
      const outcome = await uploadFiles(projectForUpload, files, setUploadProgress);
      const sent = new Set(outcome.uploaded);
      const message = describeUploadOutcome(outcome);
      if (message) setError(message);

      const accepted = newItems.filter((_, index) => sent.has(files[index]));
      const acceptedKeys = new Set(accepted.map((item) => item.key));

      setUploads((previous) =>
        previous.map((item) => {
          if (!newItems.some((entry) => entry.key === item.key)) return item;
          return acceptedKeys.has(item.key)
            ? { ...item, status: "PROCESSING", label: "Processing" }
            : { ...item, status: "FAILED", label: "Not uploaded" };
        }),
      );

      if (accepted.length) watchUploads(projectForUpload, accepted, since);
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  }

  async function stopUpload(item) {
    const markAs = (status) =>
      setUploads((previous) =>
        previous.map((upload) =>
          upload.key === item.key
            ? { ...upload, status, label: statusText(status) }
            : upload,
        ),
      );

    // Show it stopped at once; the request kills the work in the background.
    markAs("CANCELLED");
    try {
      await stopDocument(item.documentId);
    } catch (err) {
      // 409: it finished in the meantime; the status watch shows the result.
      if (err.status !== 409) {
        markAs(item.status);
        setError(err.message);
      }
    }
  }

  function handleFilesSelected(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    addFiles(files);
  }

  function formatSize(bytes) {
    if (!Number.isFinite(bytes)) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  const panelWidth = Math.min(560, window.innerWidth - 300);
  const panelHeight = Math.min(640, window.innerHeight - 160);
  const gap = 14;
  const ballRadius = 32;

  // Original ball-to-window positioning behavior preserved.
  const panelLeft = Math.max(
    12,
    Math.min(
      position.x < window.innerWidth / 2
        ? position.x + ballRadius + gap
        : position.x - ballRadius - gap - panelWidth,
      window.innerWidth - panelWidth - 12,
    ),
  );

  const panelTop = Math.max(
    12,
    Math.min(
      position.y - ballRadius - panelHeight / 2,
      window.innerHeight - panelHeight - 12,
    ),
  );

  const panelStyle = {
    left: `${panelLeft}px`,
    top: `${panelTop}px`,
  };

  return (
    <>
      {isOpen && (
        <section
          className="infer-ai-panel"
          style={panelStyle}
          aria-label="ContextAPI assistant"
        >
          <header className="infer-ai-panel-header">
            <div className="infer-ai-panel-brand">
              <span className="infer-ai-mini-orb">
                <Sparkles size={20} />
              </span>
              <div>
                <h3>ContextAPI Assistant</h3>
                <p>Enterprise knowledge assistant</p>
              </div>
            </div>

            <div className="infer-ai-header-actions">
              <button
                type="button"
                className="infer-ai-close"
                onClick={newConversation}
                disabled={sending || !turns.length}
                aria-label="New conversation"
                title="New conversation"
              >
                <RotateCcw size={18} />
              </button>

              <button
                type="button"
                className="infer-ai-close"
                onClick={() => setIsOpen(false)}
                aria-label="Close assistant"
              >
                <X size={20} />
              </button>
            </div>
          </header>

          <div className="infer-ai-project-select" ref={projectSelectRef}>
            <label htmlFor="infer-ai-project-search">Selected project</label>

            <div className="infer-ai-project-search-wrap">
              <Search size={16} />

              <input
                id="infer-ai-project-search"
                type="text"
                value={projectSearch}
                placeholder={
                  loadingProjects ? "Loading projects..." : "Search projects..."
                }
                onFocus={() => setProjectMenuOpen(true)}
                onChange={(event) => {
                  setProjectSearch(event.target.value);
                  setProjectId("");
                  setProjectMenuOpen(true);
                }}
                autoComplete="off"
                disabled={loadingProjects || sending || uploading}
              />

              <ChevronDown
                size={16}
                className={
                  projectMenuOpen ? "project-chevron open" : "project-chevron"
                }
              />
            </div>

            {projectMenuOpen && (
              <div className="infer-ai-project-results">
                {loadingProjects ? (
                  <div className="infer-ai-project-empty">
                    <LoaderCircle size={15} />
                    Loading projects...
                  </div>
                ) : filteredProjects.length ? (
                  filteredProjects.map((project) => {
                    const id = String(project.project_id ?? project.id ?? "");
                    const name = String(
                      project.name ??
                        project.project_name ??
                        project.project_id ??
                        id,
                    );

                    return (
                      <button
                        type="button"
                        className={`infer-ai-project-option ${
                          projectId === id ? "selected" : ""
                        }`}
                        key={id}
                        onClick={() => selectProject(project)}
                      >
                        <span>{name}</span>
                        {projectId === id && <CheckCircle2 size={15} />}
                      </button>
                    );
                  })
                ) : (
                  <div className="infer-ai-project-empty">
                    No matching projects found.
                  </div>
                )}
              </div>
            )}

            {selectedProject && (
              <p className="infer-ai-selected-project">
                Uploads and questions use{" "}
                <strong>
                  {selectedProject.name ??
                    selectedProject.project_name ??
                    projectId}
                </strong>
              </p>
            )}
          </div>

          <div
            className="infer-ai-conversation"
            ref={conversationRef}
            onScroll={(event) => {
              const el = event.currentTarget;
              stickToBottom.current =
                el.scrollHeight - el.scrollTop - el.clientHeight < 80;
            }}
          >
            {turns.length === 0 && uploads.length === 0 ? (
              <div className="infer-ai-welcome">
                <span className="infer-ai-welcome-icon">
                  <Bot size={30} />
                </span>
                <h2>What would you like to know?</h2>
                <p>
                  Select a project, ask questions about its knowledge, or attach
                  documents to upload them.
                </p>
                {projectId && (
                  <div className="infer-ai-suggestions">
                    {SUGGESTIONS.map((suggestion) => (
                      <button
                        type="button"
                        key={suggestion}
                        className="infer-ai-suggestion"
                        onClick={() => ask(suggestion)}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <>
                {turns.map((turn) => (
                  <AssistantTurn
                    key={turn.id}
                    turn={turn}
                    onCancel={() => cancel(turn)}
                    onRetry={() => retry(turn)}
                  />
                ))}

                {uploads.map((item) => (
                  <div className="infer-ai-upload-item" key={item.key}>
                    <span className="infer-ai-upload-icon">
                      {item.isZip ? (
                        <FileArchive size={21} />
                      ) : (
                        <FileText size={21} />
                      )}
                    </span>

                    <div className="infer-ai-upload-details">
                      <strong>{item.name}</strong>
                      <span>
                        {item.isZip ? "ZIP archive" : "Document"}
                        {item.size ? ` · ${formatSize(item.size)}` : ""}
                      </span>

                      <span className="infer-ai-upload-status">
                        {PENDING_STATUSES.includes(item.status) ? (
                          <LoaderCircle size={13} className="infer-ai-spin" />
                        ) : READY_STATUSES.includes(item.status) ? (
                          <CheckCircle2 size={13} />
                        ) : FAILED_STATUSES.includes(item.status) ? (
                          <AlertCircle size={13} />
                        ) : null}
                        {item.status === "UPLOADING" && uploadProgress
                          ? `Uploading ${uploadPercent(uploadProgress)}%`
                          : item.label}
                      </span>
                    </div>

                    {item.documentId &&
                      PENDING_STATUSES.includes(item.status) &&
                      item.status !== "UPLOADING" && (
                        <button
                          type="button"
                          className="infer-ai-upload-stop"
                          onClick={() => stopUpload(item)}
                          aria-label={`Stop processing ${item.name}`}
                          title="Stop processing"
                        >
                          <Square size={12} fill="currentColor" />
                          Stop
                        </button>
                      )}
                  </div>
                ))}
              </>
            )}
          </div>

          {error && (
            <div className="infer-ai-error" role="alert">
              {error}
            </div>
          )}

          {uploading && (
            <div className="infer-ai-uploading-note">
              <span>
                Uploading to the selected project
                {uploadProgress ? ` · ${uploadPercent(uploadProgress)}%` : "..."}
              </span>
              <span className="infer-ai-progress">
                <span style={{ width: `${uploadPercent(uploadProgress)}%` }} />
              </span>
            </div>
          )}

          <form className="infer-ai-message-form" onSubmit={handleSend}>
            <input
              ref={fileInputRef}
              type="file"
              hidden
              multiple
              accept={UPLOAD_ACCEPT}
              onChange={handleFilesSelected}
            />

            <button
              type="button"
              className="infer-ai-attach"
              onClick={() => fileInputRef.current?.click()}
              disabled={!projectId || uploading}
              aria-label="Upload documents to selected project"
              title="Attach documents"
            >
              <Paperclip size={19} />
            </button>

            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={
                projectId
                  ? "Ask ContextAPI anything..."
                  : "Select a project first..."
              }
              rows={2}
              maxLength={4000}
              aria-label="Your message"
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  event.currentTarget.form.requestSubmit();
                }
              }}
            />

            <select
              className="infer-ai-mode"
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              title={MODES.find((m) => m.value === mode)?.hint}
              aria-label="Answer mode"
            >
              {MODES.map((m) => (
                <option key={m.value} value={m.value} title={m.hint}>
                  {m.label}
                </option>
              ))}
            </select>

            <button
              type="submit"
              disabled={!message.trim() || !projectId}
              aria-label="Send message"
            >
              <Send size={18} />
            </button>
          </form>
        </section>
      )}

      <button
        type="button"
        className="infer-ai-floating-ball"
        style={{
          left: position.x - 32,
          top: position.y - 32,
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => {
          dragRef.current = null;
        }}
        aria-label="Move or open ContextAPI assistant"
      >
        {isOpen ? (
          <X size={25} />
        ) : (
          <img
            src="/images/inferai-orbital-mark.png"
            alt="ContextAPI"
            className="infer-ai-ball-logo"
            draggable="false"
          />
        )}
      </button>
    </>
  );
}
