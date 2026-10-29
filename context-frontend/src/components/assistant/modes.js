// Answer modes offered by the assistant (backend execution profiles).
export const MODES = [
  { value: "DEEP", label: "Answer", hint: "Searches your documents and writes an answer with sources" },
  { value: "COLLABORATIVE", label: "Answer+", hint: "Like Answer, with a fallback model when the local one fails" },
  { value: "STANDARD", label: "Search", hint: "Finds the most relevant passages without writing an answer (fast)" },
];
