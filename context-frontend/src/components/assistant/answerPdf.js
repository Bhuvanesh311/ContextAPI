// "Download PDF" for an answer: question, answer (same format as on screen),
// partial-coverage notice and cited sources. Built with jsPDF (loaded on first
// use) as real, selectable text. jsPDF's built-in fonts only cover Latin-1, so
// an answer in another script (Tamil, …) opens the browser's print dialog
// instead, where "Save as PDF" renders it correctly.

import { parseAnswerBlocks, parseInline } from "./answerFormat";

const PAGE = { width: 210, height: 297, left: 18, right: 18, top: 18, bottom: 22 };
const CONTENT_WIDTH = PAGE.width - PAGE.left - PAGE.right;
const PT = 0.3528; // mm per point

const COLOR = {
  text: [48, 36, 28],
  muted: [122, 106, 94],
  copper: [166, 92, 48],
  copperDark: [107, 52, 23],
  fill: [251, 243, 234],
  rule: [234, 216, 199],
};

// Typographic characters jsPDF's standard fonts cannot encode reliably.
const REPLACEMENTS = [
  [/[‘’‚′]/g, "'"],
  [/[“”„″]/g, '"'],
  [/[–—−]/g, "-"],
  [/…/g, "..."],
  [/[•●▪]/g, "-"],
  [/₹/g, "Rs. "],
  [/€/g, "EUR "],
  [/[   ]/g, " "],
  [/→/g, "->"],
  [/←/g, "<-"],
  [/[✓✔]/g, "v"],
  [/×/g, "x"],
  [/[​-‍﻿]/g, ""],
];

function sanitize(text) {
  return REPLACEMENTS.reduce((s, [re, to]) => s.replace(re, to), String(text ?? ""));
}

const needsUnicode = (text) => /[^\u0000-ÿ]/.test(sanitize(text));

// PDF literal strings: backslash and parentheses must be escaped.
const escapePdfString = (text) => text.replace(/[\\()]/g, (c) => "\\" + c);

/**
 * export = { question, answer, notice, sources: [{ citation, name }], meta }
 * Returns "pdf" or "print" (the fallback that was used).
 */
export async function downloadAnswerPdf(data) {
  const texts = [data.question, data.answer, data.notice, ...data.sources.map((s) => s.name)];
  if (texts.some(needsUnicode)) {
    printAnswer(data);
    return "print";
  }
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  new Writer(doc).render(data);
  doc.save(fileName(data.question));
  return "pdf";
}

function fileName(question) {
  const slug = sanitize(question)
    .replace(/[^\w\s-]/g, "")
    .trim()
    .split(/\s+/)
    .slice(0, 6)
    .join("-")
    .toLowerCase();
  return `ContextAPI-${slug || "answer"}.pdf`;
}

function exportDate() {
  return new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

class Writer {
  constructor(doc) {
    this.doc = doc;
    this.y = PAGE.top;
    this.date = exportDate();
  }

  render({ question, answer, notice, sources, meta }) {
    this.header();
    this.questionBox(question);
    this.label("Answer");
    for (const block of parseAnswerBlocks(sanitize(answer))) this.block(block);
    if (notice) this.noticeBox(notice);
    if (sources.length) this.sourceList(sources);
    if (meta) this.metaLine(meta);
    this.footers();
  }

  // ---- layout primitives ---------------------------------------------
  style(kind, size) {
    const { doc } = this;
    if (kind === "code") doc.setFont("courier", "normal");
    else doc.setFont("helvetica", kind === "bold" || kind === "cite" ? "bold" : kind === "italic" ? "italic" : "normal");
    doc.setFontSize(kind === "cite" ? size * 0.72 : size);
    doc.setTextColor(...(kind === "cite" ? COLOR.copper : this.color ?? COLOR.text));
  }

  ensure(height) {
    if (this.y + height <= PAGE.height - PAGE.bottom) return;
    this.doc.addPage();
    this.y = PAGE.top;
  }

  // Word-wrap mixed-style tokens into lines of measured pieces. Pieces with
  // no space between them ("deals", "[3]", ".") wrap as one unit.
  wrap(tokens, width, size) {
    const groups = [];
    // Style of the whitespace before the next word (null = none): a space
    // keeps its own token's style, so text before `code` gets a normal gap.
    let spaceKind = null;
    for (const tok of tokens) {
      const kind = tok.type === "cite" ? "cite" : tok.type === "text" ? this.baseKind ?? "normal" : tok.type;
      const parts = tok.type === "cite" ? [`[${tok.value}]`] : tok.value.split(/(\s+)/);
      for (const part of parts) {
        if (!part) continue;
        if (/^\s+$/.test(part)) {
          spaceKind = kind;
          continue;
        }
        this.style(kind, size);
        const piece = { kind, text: part, width: this.doc.getTextWidth(part) };
        if (!spaceKind && groups.length) groups.at(-1).pieces.push(piece);
        else groups.push({ space: spaceKind, pieces: [piece] });
        spaceKind = null;
      }
    }

    // jsPDF measures a little narrower than viewers draw; keep a margin.
    const limit = width * 0.985;
    const lines = [[]];
    let used = 0;
    for (const group of groups) {
      const w = group.pieces.reduce((sum, p) => sum + p.width, 0);
      let spaceW = 0;
      if (group.space && lines.at(-1).length) {
        this.style(group.space, size);
        spaceW = this.doc.getTextWidth(" ");
      }
      if (used + spaceW + w > limit && lines.at(-1).length) {
        lines.push([]);
        used = 0;
        spaceW = 0;
      }
      if (spaceW) {
        lines.at(-1).push({ kind: group.space, text: " ", width: spaceW });
        used += spaceW;
      }
      for (const piece of group.pieces) {
        // A single word wider than the line is broken by characters.
        if (piece.width <= limit) {
          lines.at(-1).push(piece);
          used += piece.width;
          continue;
        }
        this.style(piece.kind, size);
        let chunk = "";
        for (const ch of piece.text) {
          if (chunk && used + this.doc.getTextWidth(chunk + ch) > limit) {
            lines.at(-1).push({ ...piece, text: chunk, width: this.doc.getTextWidth(chunk) });
            lines.push([]);
            used = 0;
            chunk = "";
          }
          chunk += ch;
        }
        const cw = this.doc.getTextWidth(chunk);
        lines.at(-1).push({ ...piece, text: chunk, width: cw });
        used += cw;
      }
    }
    return lines.filter((l) => l.length);
  }

  // One text object per line: each style run continues where the viewer
  // finished drawing the previous one, so spacing is exact in any viewer
  // (jsPDF's own widths are ~1% off for some glyphs).
  drawLine(line, x, size) {
    const { doc } = this;
    const k = doc.internal.scaleFactor;
    const fmt = (n) => Number(n.toFixed(3));
    // Reset text state: labels drawn with charSpace leave Tc set.
    const ops = ["BT", "0 Tc 0 Tw 100 Tz", `${fmt(x * k)} ${fmt((PAGE.height - this.y) * k)} Td`];
    let current = null;
    for (const piece of line) {
      if (piece.kind !== current) {
        current = piece.kind;
        const cite = piece.kind === "cite";
        const font = piece.kind === "code"
          ? doc.internal.getFont("courier", "normal")
          : doc.internal.getFont("helvetica", cite || piece.kind === "bold" ? "bold" : piece.kind === "italic" ? "italic" : "normal");
        const color = (cite ? COLOR.copper : this.color ?? COLOR.text).map((c) => fmt(c / 255));
        ops.push(`/${font.id} ${fmt(cite ? size * 0.72 : size)} Tf`, `${color.join(" ")} rg`, `${cite ? fmt(size * 0.3) : 0} Ts`);
      }
      ops.push(`(${escapePdfString(piece.text)}) Tj`);
    }
    ops.push("0 Ts", "ET");
    doc.internal.write(ops.join("\n"));
  }

  // Wrap and draw text at x, breaking pages as needed.
  rich(text, { x = PAGE.left, width = CONTENT_WIDTH, size = 10.5, gap = 1.45, onLine } = {}) {
    const lineHeight = size * PT * gap;
    const lines = this.wrap(parseInline(text), width, size);
    lines.forEach((line, i) => {
      this.ensure(lineHeight);
      this.y += lineHeight;
      if (i === 0 && onLine) onLine();
      this.drawLine(line, x, size);
    });
    return lines.length;
  }

  // ---- sections ------------------------------------------------------
  header() {
    const { doc } = this;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(18);
    doc.setTextColor(...COLOR.copperDark);
    doc.text("Context", PAGE.left, this.y + 6);
    const w = doc.getTextWidth("Context");
    doc.setTextColor(...COLOR.copper);
    doc.text("API", PAGE.left + w, this.y + 6);

    doc.setFont("helvetica", "normal");
    doc.setFontSize(8.5);
    doc.setTextColor(...COLOR.muted);
    doc.text("ANSWER EXPORT", PAGE.width - PAGE.right, this.y + 2.5, { align: "right" });
    doc.text(this.date, PAGE.width - PAGE.right, this.y + 6.5, { align: "right" });

    this.y += 10;
    doc.setDrawColor(...COLOR.copper);
    doc.setLineWidth(0.6);
    doc.line(PAGE.left, this.y, PAGE.left + 28, this.y);
    doc.setDrawColor(...COLOR.rule);
    doc.setLineWidth(0.3);
    doc.line(PAGE.left + 28, this.y, PAGE.width - PAGE.right, this.y);
    this.y += 7;
  }

  questionBox(question) {
    const size = 11.5;
    const pad = 4.5;
    const inner = CONTENT_WIDTH - pad * 2 - 2;
    this.baseKind = "bold";
    const lines = this.wrap(parseInline(sanitize(question)), inner, size);
    const lineHeight = size * PT * 1.4;
    const height = pad * 2 + 5 + lines.length * lineHeight;

    this.ensure(Math.min(height, 60));
    const { doc } = this;
    doc.setFillColor(...COLOR.fill);
    doc.roundedRect(PAGE.left, this.y, CONTENT_WIDTH, height, 2.5, 2.5, "F");
    doc.setFillColor(...COLOR.copper);
    doc.rect(PAGE.left, this.y, 1.2, height, "F");

    const top = this.y;
    this.y += pad + 2;
    this.smallCaps("Question", PAGE.left + pad + 2);
    this.y += 1;
    for (const line of lines) {
      this.y += lineHeight;
      this.drawLine(line, PAGE.left + pad + 2, size);
    }
    this.baseKind = null;
    this.y = top + height + 8;
  }

  smallCaps(text, x = PAGE.left) {
    const { doc } = this;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(7.5);
    doc.setTextColor(...COLOR.muted);
    doc.text(text.toUpperCase(), x, this.y, { charSpace: 0.6 });
  }

  label(text) {
    this.ensure(10);
    this.smallCaps(text);
    this.y += 2;
  }

  block(block) {
    if (block.type === "heading") {
      this.ensure(12);
      this.y += 2.5;
      this.baseKind = "bold";
      this.color = COLOR.copperDark;
      this.rich(block.text, { size: 12.5, gap: 1.3 });
      this.baseKind = null;
      this.color = null;
      this.y += 1.5;
      return;
    }

    if (block.type === "paragraph") {
      for (const line of block.lines) this.rich(line);
      this.y += 3;
      return;
    }

    const counters = [0, 0, 0, 0];
    for (const item of block.items) {
      counters[item.depth] += 1;
      counters.fill(0, item.depth + 1);
      const indent = 6 + item.depth * 6;
      const markerX = PAGE.left + indent - 4.5;
      this.rich(item.text, {
        x: PAGE.left + indent,
        width: CONTENT_WIDTH - indent,
        onLine: () => this.marker(block.ordered, counters[item.depth], item.depth, markerX),
      });
      this.y += 1;
    }
    this.y += 2.5;
  }

  marker(ordered, n, depth, x) {
    const { doc } = this;
    if (ordered) {
      doc.setFont("helvetica", "bold");
      doc.setFontSize(10);
      doc.setTextColor(...COLOR.copper);
      doc.text(`${n}.`, x, this.y);
      return;
    }
    doc.setFillColor(...COLOR.copper);
    doc.setDrawColor(...COLOR.copper);
    if (depth === 0) doc.circle(x + 1, this.y - 1.3, 0.75, "F");
    else doc.circle(x + 1, this.y - 1.3, 0.65, "S");
  }

  noticeBox(notice) {
    const size = 9.5;
    const pad = 3.5;
    this.baseKind = "italic";
    this.color = COLOR.copperDark;
    const lines = this.wrap(parseInline(sanitize(notice)), CONTENT_WIDTH - pad * 2 - 2, size);
    const height = pad * 2 + lines.length * size * PT * 1.4;
    this.ensure(height + 4);
    this.y += 1;

    const { doc } = this;
    doc.setFillColor(...COLOR.fill);
    doc.rect(PAGE.left, this.y, CONTENT_WIDTH, height, "F");
    doc.setFillColor(...COLOR.copper);
    doc.rect(PAGE.left, this.y, 1, height, "F");

    const top = this.y;
    this.y += pad - 0.5;
    for (const line of lines) {
      this.y += size * PT * 1.4;
      this.drawLine(line, PAGE.left + pad + 2, size);
    }
    this.baseKind = null;
    this.color = null;
    this.y = top + height + 5;
  }

  sourceList(sources) {
    this.ensure(16);
    this.y += 2;
    const { doc } = this;
    doc.setDrawColor(...COLOR.rule);
    doc.setLineWidth(0.3);
    doc.line(PAGE.left, this.y, PAGE.width - PAGE.right, this.y);
    this.y += 6;
    this.label("Sources");
    for (const source of sources) {
      const size = 9.5;
      this.ensure(size * PT * 1.5);
      this.y += size * PT * 1.5;
      doc.setFont("helvetica", "bold");
      doc.setFontSize(size);
      doc.setTextColor(...COLOR.copper);
      doc.text(`[${source.citation}]`, PAGE.left, this.y);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(...COLOR.text);
      const name = doc.splitTextToSize(sanitize(source.name), CONTENT_WIDTH - 10)[0];
      doc.text(name, PAGE.left + 10, this.y);
    }
    this.y += 4;
  }

  metaLine(meta) {
    this.ensure(8);
    this.y += 3;
    const { doc } = this;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8.5);
    doc.setTextColor(...COLOR.muted);
    doc.text(sanitize(meta), PAGE.left, this.y);
  }

  footers() {
    const { doc } = this;
    const pages = doc.getNumberOfPages();
    for (let i = 1; i <= pages; i += 1) {
      doc.setPage(i);
      const y = PAGE.height - 12;
      doc.setDrawColor(...COLOR.rule);
      doc.setLineWidth(0.3);
      doc.line(PAGE.left, y - 4, PAGE.width - PAGE.right, y - 4);
      doc.setFont("helvetica", "normal");
      doc.setFontSize(8);
      doc.setTextColor(...COLOR.muted);
      doc.text(`Generated by ContextAPI  |  ${this.date}`, PAGE.left, y);
      doc.text(`Page ${i} of ${pages}`, PAGE.width - PAGE.right, y, { align: "right" });
    }
  }
}

// ---- print fallback (any script) ---------------------------------------
function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function inlineHtml(text) {
  return parseInline(text)
    .map((tok) => {
      if (tok.type === "bold") return `<strong>${escapeHtml(tok.value)}</strong>`;
      if (tok.type === "code") return `<code>${escapeHtml(tok.value)}</code>`;
      if (tok.type === "cite") return `<sup>[${escapeHtml(tok.value)}]</sup>`;
      return escapeHtml(tok.value);
    })
    .join("");
}

function answerHtml(answer) {
  return parseAnswerBlocks(answer)
    .map((block) => {
      if (block.type === "heading") return `<h2>${inlineHtml(block.text)}</h2>`;
      if (block.type === "paragraph") return `<p>${block.lines.map(inlineHtml).join("<br>")}</p>`;
      const tag = block.ordered ? "ol" : "ul";
      const items = block.items
        .map((item) => `<li style="margin-left:${item.depth * 18}px">${inlineHtml(item.text)}</li>`)
        .join("");
      return `<${tag}>${items}</${tag}>`;
    })
    .join("");
}

function printAnswer({ question, answer, notice, sources, meta }) {
  const win = window.open("", "_blank");
  if (!win) throw new Error("Allow pop-ups for this site to save the answer as PDF.");
  const date = exportDate();
  win.document.write(`<!doctype html><html><head><meta charset="utf-8">
<title>${escapeHtml(fileName(question).replace(/\.pdf$/, ""))}</title>
<style>
  @page { size: A4; margin: 18mm; }
  body { font: 11pt/1.55 "Segoe UI", "Noto Sans", "Noto Sans Tamil", system-ui, sans-serif; color: #30241c; margin: 0; }
  header { display: flex; justify-content: space-between; align-items: end; border-bottom: 1px solid #ead8c7; padding-bottom: 8px; margin-bottom: 18px; }
  .brand { font: 700 20pt Georgia, serif; color: #6b3417; } .brand em { font-style: normal; color: #a65c30; }
  .stamp { text-align: right; font-size: 8.5pt; color: #7a6a5e; letter-spacing: .04em; }
  .label { font-size: 7.5pt; font-weight: 700; letter-spacing: .12em; color: #7a6a5e; text-transform: uppercase; }
  .question { background: #fbf3ea; border-left: 4px solid #a65c30; border-radius: 6px; padding: 10px 14px; margin-bottom: 18px; }
  .question p { margin: 4px 0 0; font-weight: 700; }
  h2 { font-size: 12.5pt; color: #6b3417; margin: 14px 0 4px; }
  sup { color: #a65c30; font-weight: 700; font-size: 7pt; }
  code { font-family: Consolas, monospace; background: #f5ebe1; padding: 0 3px; border-radius: 3px; }
  .notice { background: #fbf3ea; border-left: 3px solid #a65c30; padding: 6px 10px; font-style: italic; color: #6b3417; }
  .sources { border-top: 1px solid #ead8c7; margin-top: 18px; padding-top: 10px; }
  .sources div { font-size: 9.5pt; } .sources b { color: #a65c30; margin-right: 8px; }
  .meta { font-size: 8.5pt; color: #7a6a5e; margin-top: 10px; }
  footer { margin-top: 24px; font-size: 8pt; color: #7a6a5e; }
</style></head><body>
<header><div class="brand">Context<em>API</em></div><div class="stamp">ANSWER EXPORT<br>${escapeHtml(date)}</div></header>
<div class="question"><div class="label">Question</div><p>${escapeHtml(question)}</p></div>
<div class="label">Answer</div>
${answerHtml(answer)}
${notice ? `<p class="notice">${escapeHtml(notice)}</p>` : ""}
${sources.length ? `<div class="sources"><div class="label">Sources</div>${sources.map((s) => `<div><b>[${escapeHtml(s.citation)}]</b>${escapeHtml(s.name)}</div>`).join("")}</div>` : ""}
${meta ? `<div class="meta">${escapeHtml(meta)}</div>` : ""}
<footer>Generated by ContextAPI | ${escapeHtml(date)}</footer>
</body></html>`);
  win.document.close();
  win.focus();
  win.onafterprint = () => win.close();
  setTimeout(() => win.print(), 250);
}
