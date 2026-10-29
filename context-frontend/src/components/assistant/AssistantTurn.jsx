import { useEffect, useState } from "react";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  FileDown,
  FileUp,
  Loader2,
  Lightbulb,
  SearchX,
  Square,
  RotateCw,
} from "lucide-react";
import { MODES } from "./modes";
import { parseAnswerBlocks, parseInline } from "./answerFormat";
import { downloadAnswerPdf } from "./answerPdf";

const STAGE_TEXT = {
  queued: "Starting…",
  indexing: "Waiting for your documents to finish processing…",
  searching: "Searching your documents…",
  writing: "Reading the passages and writing an answer…",
};

function Elapsed({ since }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  return <>{Math.max(0, Math.round((now - since) / 1000))}s</>;
}

/**
 * One question and its answer. `turn` holds { question, profile, pending,
 * stage, partial, answer, error, cancelled, requestId, startedAt, elapsedMs }.
 */
export default function AssistantTurn({ turn, onCancel, onRetry }) {
  const [highlight, setHighlight] = useState(null);
  const [showSources, setShowSources] = useState(false);
  const [copied, setCopied] = useState(false);
  // null | "busy" | error message
  const [pdfState, setPdfState] = useState(null);

  const a = turn.answer;
  const failed = a && (a.status === "FAILED" || a.status === "CANCELLED");
  const writes = turn.profile === "DEEP" || turn.profile === "COLLABORATIVE";
  // The backend judges document coverage for every mode; off-topic questions
  // show its notice instead of an answer or "relevant" passages.
  const offTopic = a?.relevance === "not_relevant" || a?.relevance === "no_documents";
  const answerText = offTopic ? null : a?.answer;
  const cited = a?.cited_sources ?? [];
  const sources = a ? (cited.length ? cited : a.top_results ?? []) : [];
  // "Only X of Y claims are supported…" is shown as a small chip instead of a
  // warning box; other warnings stay visible.
  const claims = (a?.warnings ?? [])
    .map((w) => /Only (\d+) of (\d+) claims are supported/.exec(w))
    .find(Boolean);
  const warnings = (a?.warnings ?? []).filter(
    (w) => !/claims are supported by their cited evidence/.test(w),
  );
  // The cited list only names documents; take the passage text from the search results.
  const snippetFor = (source) =>
    source.snippet ??
    a?.top_results?.find((r) => r.citation === source.citation)?.snippet ??
    null;

  async function savePdf() {
    if (!answerText || pdfState === "busy") return;
    setPdfState("busy");
    try {
      const mode = MODES.find((m) => m.value === turn.profile)?.label ?? turn.profile;
      await downloadAnswerPdf({
        question: turn.question,
        answer: answerText,
        notice: a.relevance === "partial" ? a.notice : null,
        sources: cited
          .filter((s, i) => cited.findIndex((o) => o.citation === s.citation) === i)
          .map((s) => ({ citation: s.citation, name: s.document_name ?? s.document_id ?? "Document" })),
        meta: [
          mode && `${mode} mode`,
          a.grounding_score != null && `${Math.round(a.grounding_score * 100)}% grounded`,
        ]
          .filter(Boolean)
          .join("  |  "),
      });
      setPdfState(null);
    } catch (err) {
      setPdfState(err.message || "Could not create the PDF.");
    }
  }

  async function copy() {
    if (!answerText) return;
    try {
      await navigator.clipboard.writeText(answerText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked; nothing to do.
    }
  }

  return (
    <div className="infer-ai-turn">
      <div className="infer-ai-message user">{turn.question}</div>

      <div className="infer-ai-message assistant infer-ai-answer-bubble">
        {turn.pending ? (
          <>
            {turn.partial ? (
              <AnswerText text={turn.partial} onCite={() => {}} streaming />
            ) : (
              <div className="infer-ai-thinking">
                <span className="infer-ai-dots">
                  <i />
                  <i />
                  <i />
                </span>
                <span>{STAGE_TEXT[turn.stage ?? "queued"] ?? "Working…"}</span>
              </div>
            )}
            <div className="infer-ai-meta">
              <span>
                <Elapsed since={turn.startedAt} />
              </span>
              <button type="button" className="infer-ai-link" onClick={onCancel}>
                <Square size={11} /> Stop
              </button>
            </div>
          </>
        ) : turn.error ? (
          <div className="infer-ai-turn-error">
            <AlertCircle size={15} />
            <span>{turn.error}</span>
            {turn.requestId && !turn.cancelled && (
              <button type="button" className="infer-ai-link" onClick={onRetry}>
                <RotateCw size={12} /> Check again
              </button>
            )}
          </div>
        ) : a ? (
          <>
            {failed ? (
              <div className="infer-ai-turn-error">
                <AlertCircle size={15} />
                <span>{a.error_message || `Request ${String(a.status).toLowerCase()}.`}</span>
              </div>
            ) : offTopic ? (
              <div className="infer-ai-notice" role="status">
                <span className="infer-ai-notice-badge" aria-hidden="true">
                  {a.relevance === "no_documents" ? <FileUp size={18} /> : <SearchX size={18} />}
                  <i className="infer-ai-notice-orbit" />
                </span>
                <div className="infer-ai-notice-body">
                  <strong>
                    {a.relevance === "no_documents" ? "No documents to search yet" : "Not found in your documents"}
                  </strong>
                  <p>{a.notice}</p>
                  <span className="infer-ai-notice-tip">
                    <Lightbulb size={12} />
                    {a.relevance === "no_documents"
                      ? "Use the paperclip button below to add PDFs, Office files, images or code."
                      : "Tip: use words that appear in your files, or name the document you mean."}
                  </span>
                </div>
              </div>
            ) : answerText ? (
              <>
                <AnswerText text={answerText} onCite={setHighlight} />
                {a.relevance === "partial" && a.notice && (
                  <div className="infer-ai-notice-partial" role="note">
                    <span className="infer-ai-notice-meter" aria-hidden="true">
                      <i />
                    </span>
                    <span>
                      <b>Partial coverage</b> · {a.notice}
                    </span>
                  </div>
                )}
              </>
            ) : (
              <p className="infer-ai-muted">
                {writes
                  ? "The documents in this project don't seem to cover this question. Try asking about something in them, or upload a file that covers it."
                  : sources.length
                    ? "Most relevant passages:"
                    : "Nothing relevant was found in this project's documents."}
              </p>
            )}

            {warnings.length > 0 && answerText && (
              <ul className="infer-ai-warnings">
                {warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}

            {sources.length > 0 && (
              <div className="infer-ai-sources">
                {(answerText || writes || offTopic) && (
                  <button
                    type="button"
                    className="infer-ai-sources-toggle"
                    onClick={() => setShowSources(!showSources)}
                  >
                    {showSources ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    {answerText ? "" : offTopic ? "Closest passages (may not be related): " : "Closest passages: "}
                    {sources.length} source{sources.length > 1 ? "s" : ""} ·{" "}
                    {[...new Set(sources.map((s) => s.document_name ?? "Document"))].join(", ")}
                  </button>
                )}
                {/* Search mode shows passages directly; answers keep them folded. */}
                {(showSources || (!answerText && !writes && !offTopic)) &&
                  sources.map((s, i) => (
                    <SourceCard
                      key={i}
                      source={s}
                      snippet={snippetFor(s)}
                      index={i}
                      active={highlight != null && s.citation === highlight}
                    />
                  ))}
              </div>
            )}

            <div className="infer-ai-meta">
              {answerText && (
                <button type="button" className="infer-ai-link" onClick={copy}>
                  {copied ? <Check size={12} /> : <Copy size={12} />}
                  {copied ? "Copied" : "Copy"}
                </button>
              )}
              {answerText && (
                <button
                  type="button"
                  className="infer-ai-link"
                  onClick={savePdf}
                  disabled={pdfState === "busy"}
                  title="Download this question and answer as a PDF"
                >
                  {pdfState === "busy" ? <Loader2 size={12} className="infer-ai-spin" /> : <FileDown size={12} />}
                  {pdfState === "busy" ? "Preparing…" : "PDF"}
                </button>
              )}
              {pdfState && pdfState !== "busy" && <span className="infer-ai-pdf-error">{pdfState}</span>}
              {turn.elapsedMs != null && <span>{(turn.elapsedMs / 1000).toFixed(0)}s</span>}
              {a.grounding_score != null && answerText && (
                <span title="Share of the passages given to the model that the answer cites">
                  {Math.round(a.grounding_score * 100)}% grounded
                </span>
              )}
              {claims && (
                <span
                  className="infer-ai-chip"
                  title="Sentences that state a fact and cite a passage supporting it. Uncited sentences may still be right; check the sources."
                >
                  {claims[1]}/{claims[2]} claims cited
                </span>
              )}
              {/* Flag only weakly supported answers as partial (the notice covers newer answers). */}
              {a.status === "PARTIAL" && answerText && !a.notice && (a.grounding_score ?? 0) < 0.8 && (
                <span
                  className="infer-ai-chip warn"
                  title="The documents only partly cover this question, so the answer may be incomplete. A more specific question usually helps."
                >
                  Partial evidence
                </span>
              )}
              {turn.profile !== "DEEP" && (
                <span>{MODES.find((m) => m.value === turn.profile)?.label ?? turn.profile}</span>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

function SourceCard({ source, snippet, index, active }) {
  const [open, setOpen] = useState(false);
  const text = snippet ?? "";
  const long = text.length > 220;

  return (
    <div className={`infer-ai-source ${active ? "active" : ""}`}>
      <div className="infer-ai-source-head">
        <span className="infer-ai-cite">{source.citation ?? index + 1}</span>
        <span className="infer-ai-source-name">
          {source.document_name ?? source.document_id ?? "Document"}
        </span>
      </div>
      {text && (
        <div className="infer-ai-snippet">
          {open || !long ? text : `${text.slice(0, 220)}…`}
          {long && (
            <button type="button" className="infer-ai-link" onClick={() => setOpen(!open)}>
              {open ? "less" : "more"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// Minimal, safe renderer for the model's answer (format in answerFormat.js).
// No HTML is injected.
export function AnswerText({ text, onCite, streaming = false }) {
  return (
    <div className={`infer-ai-answer ${streaming ? "streaming" : ""}`}>
      {parseAnswerBlocks(text).map((block, i) => {
        if (block.type === "list") {
          const items = block.items.map((item, j) => (
            <li key={j} style={item.depth ? { marginLeft: item.depth * 18 } : undefined}>
              {inline(item.text, onCite)}
            </li>
          ));
          return block.ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>;
        }

        if (block.type === "heading") return <h4 key={i}>{inline(block.text, onCite)}</h4>;

        return (
          <p key={i}>
            {block.lines.map((l, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {inline(l, onCite)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function inline(text, onCite) {
  return parseInline(text).map((tok, k) => {
    if (tok.type === "bold") return <strong key={k}>{tok.value}</strong>;
    if (tok.type === "code") return <code key={k}>{tok.value}</code>;
    if (tok.type === "text") return tok.value;
    if (tok.value.startsWith("M")) {
      return (
        <sup key={k} className="infer-ai-cite-ref memory" title="From earlier in this conversation">
          {tok.value}
        </sup>
      );
    }
    const n = Number(tok.value);
    return (
      <sup
        key={k}
        className="infer-ai-cite-ref"
        onMouseEnter={() => onCite(n)}
        onMouseLeave={() => onCite(null)}
      >
        {n}
      </sup>
    );
  });
}
