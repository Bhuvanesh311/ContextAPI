// The model's answer format, shared by the on-screen renderer and the PDF
// export: paragraphs, nested bullet and numbered lists, headings, **bold**,
// `code` and [N] / [MN] citation markers.

const LIST_ITEM = /^\s*([-*•]|\d+[.)])\s+/;
const CITATIONS_ONLY = /^\s*(\[M?\d+(?:\s*,\s*M?\d+)*\]\s*)+$/;

/**
 * Split an answer into blocks:
 *   { type: "list", ordered, items: [{ depth, text }] }
 *   { type: "heading", text }
 *   { type: "paragraph", lines: [text] }
 */
export function parseAnswerBlocks(text) {
  const blocks = [];
  for (const block of text.trim().split(/\n{2,}/)) {
    const lines = block.split("\n").filter((l) => l.trim());
    if (!lines.length) continue;
    // A trailing "[1][2][4]" line on its own adds nothing to the inline citations.
    if (lines.every((l) => CITATIONS_ONLY.test(l))) continue;

    if (lines.every((l) => LIST_ITEM.test(l))) {
      blocks.push({
        type: "list",
        ordered: /^\s*\d+[.)]/.test(lines[0]),
        items: lines.map((l) => ({
          depth: Math.min(3, Math.floor((/^\s*/.exec(l)?.[0].length ?? 0) / 2)),
          text: l.replace(LIST_ITEM, ""),
        })),
      });
      continue;
    }

    const heading = /^#{1,4}\s+(.*)$/.exec(lines[0]);
    if (heading && lines.length === 1) {
      blocks.push({ type: "heading", text: heading[1] });
      continue;
    }

    blocks.push({ type: "paragraph", lines });
  }
  return blocks;
}

/**
 * Split one line into tokens:
 *   { type: "text" | "bold" | "code", value }
 *   { type: "cite", value: "3" | "M2" }   (one token per reference)
 */
export function parseInline(text) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[M?\d+(?:\s*,\s*M?\d+)*\])/g;
  let last = 0;
  let m;

  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ type: "text", value: text.slice(last, m.index) });
    const tok = m[0];

    if (tok.startsWith("**")) out.push({ type: "bold", value: tok.slice(2, -2) });
    else if (tok.startsWith("`")) out.push({ type: "code", value: tok.slice(1, -1) });
    else {
      for (const ref of tok.slice(1, -1).split(",").map((s) => s.trim())) {
        out.push({ type: "cite", value: ref });
      }
    }
    last = m.index + tok.length;
  }

  if (last < text.length) out.push({ type: "text", value: text.slice(last) });
  return out;
}
