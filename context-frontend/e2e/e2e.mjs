// End-to-end test of the ContextAPI web app's assistant, driving a locally
// installed Edge or Chrome (playwright-core: no browser download).
//
//   E2E_EMAIL=... E2E_PASSWORD=... npm run test:e2e
//
// Env: E2E_URL (default http://localhost:5173), E2E_BROWSER (msedge | chrome),
// E2E_HEADED=1 to watch it. The account must be verified. The test creates a
// project, uploads a file, asks questions and deletes the project again.
// Screenshots go to e2e/shots; a failed step exits non-zero.
import { chromium } from "playwright-core";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const UI = (process.env.E2E_URL ?? "http://localhost:5173").replace(/\/$/, "");
const EMAIL = process.env.E2E_EMAIL;
const PASSWORD = process.env.E2E_PASSWORD;
if (!EMAIL || !PASSWORD) {
  console.error("Set E2E_EMAIL and E2E_PASSWORD to a verified test account.");
  process.exit(2);
}
const FILES = path.join(HERE, "fixtures");
const SHOTS = path.join(HERE, "shots");
fs.rmSync(SHOTS, { recursive: true, force: true });
fs.mkdirSync(SHOTS, { recursive: true });

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const problems = [];
const t0 = Date.now();

const browser = await chromium.launch({
  channel: process.env.E2E_BROWSER ?? "msedge",
  headless: !process.env.E2E_HEADED,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("dialog", async (d) => {
  log(`   dialog: ${d.message()}`);
  await d.accept();
});
page.on("response", (r) => r.status() >= 500 && problems.push(`HTTP ${r.status()} ${r.url()}`));

let n = 0;
const shot = async (name) =>
  page.screenshot({ path: path.join(SHOTS, `${String(++n).padStart(2, "0")}-${name}.png`) });

async function step(name, fn) {
  const s = Date.now();
  try {
    await fn();
    log(`PASS ${name} (${((Date.now() - s) / 1000).toFixed(1)}s)`);
  } catch (e) {
    problems.push(`FAIL ${name}: ${e.message.split("\n")[0]}`);
    log(`FAIL ${name}: ${e.message.split("\n")[0]}`);
    await shot(`FAIL-${name.replace(/\W+/g, "_")}`);
  }
}

// Calls the API through the app's /backend proxy with the page's token.
async function api(pathname, init = {}) {
  return page.evaluate(
    async ([url, init]) => {
      const token = sessionStorage.getItem("inferai_access_token");
      const res = await fetch(url, {
        ...init,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      });
      return { status: res.status, body: await res.json().catch(() => null) };
    },
    [`${UI}/backend${pathname}`, init],
  );
}

/** Asks in the assistant and waits for the final answer; returns what was seen. */
async function ask(question) {
  const before = await page.locator(".infer-ai-turn").count();
  await page.fill(".infer-ai-message-form textarea", question);
  await page.press(".infer-ai-message-form textarea", "Enter");
  const turn = page.locator(".infer-ai-turn").nth(before);
  await turn.waitFor({ timeout: 10_000 });

  // Watch the bubble while it runs: stage texts and the growing partial answer.
  const stages = new Set();
  let streamedChars = 0;
  const deadline = Date.now() + 5 * 60_000;
  while (Date.now() < deadline) {
    const pending = await turn.locator(".infer-ai-thinking, .infer-ai-answer.streaming").count();
    if (!pending) break;
    // allInnerTexts() never waits: these elements vanish as the answer moves on.
    for (const text of await turn.locator(".infer-ai-thinking").allInnerTexts()) {
      stages.add(text.trim());
    }
    for (const text of await turn.locator(".infer-ai-answer.streaming").allInnerTexts()) {
      streamedChars = Math.max(streamedChars, text.length);
    }
    await page.waitForTimeout(300);
  }

  const error = turn.locator(".infer-ai-turn-error");
  if (await error.count()) throw new Error(`answer failed: ${await error.innerText()}`);
  const answer = turn.locator(".infer-ai-answer:not(.streaming)");
  await answer.waitFor({ timeout: 5_000 });
  return { text: await answer.innerText(), stages: [...stages], streamedChars, turn };
}

let projectId = null;
const projectName = `E2E assistant ${new Date().toISOString().slice(0, 19).replace(/\D/g, "")}`;

await step("login", async () => {
  await page.goto(`${UI}/`);
  await page.fill('input[placeholder="you@company.com"]', EMAIL);
  await page.fill('input[placeholder="Enter your password"]', PASSWORD);
  await page.locator('button[type="submit"]').first().click();
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
  await shot("dashboard");
});

await step("create project", async () => {
  const res = await api("/projects/", {
    method: "POST",
    body: JSON.stringify({ name: projectName, description: "Created by e2e.mjs", status: "active" }),
  });
  projectId = res.body?.project?.project_id;
  if (!projectId) throw new Error(`HTTP ${res.status}: ${JSON.stringify(res.body)}`);
});

await step("open assistant and pick project", async () => {
  await page.click(".infer-ai-floating-ball");
  await page.locator(".infer-ai-panel").waitFor();
  await page.fill("#infer-ai-project-search", projectName);
  await page.locator(".infer-ai-project-option", { hasText: projectName }).click();
  await page.locator(".infer-ai-selected-project", { hasText: projectName }).waitFor();
  await shot("assistant-open");
});

await step("upload file and wait until ready", async () => {
  await page.setInputFiles(".infer-ai-message-form input[type=file]", [
    path.join(FILES, "leave_policy.docx"),
  ]);
  const card = page.locator(".infer-ai-upload-item", { hasText: "leave_policy.docx" });
  await card.waitFor();
  await card.locator(".infer-ai-upload-status", { hasText: "Ready" }).waitFor({ timeout: 4 * 60_000 });
  await shot("file-ready");
});

await step("live answer", async () => {
  const r = await ask("How many days of annual leave do employees get?");
  log(`   stages: ${r.stages.join(" → ") || "(none seen)"}; streamed ${r.streamedChars} chars`);
  log(`   answer: ${r.text.slice(0, 160).replace(/\s+/g, " ")}`);
  if (!r.streamedChars) throw new Error("no partial answer was shown while the answer was written");
  if (!(await r.turn.locator(".infer-ai-sources-toggle").count())) throw new Error("answer has no sources");
  await r.turn.locator(".infer-ai-sources-toggle").click();
  await r.turn.locator(".infer-ai-source").first().waitFor();
  await shot("answer-with-sources");
});

await step("follow-up uses the conversation", async () => {
  const r = await ask("And how many of those can be carried over to next year?");
  log(`   answer: ${r.text.slice(0, 160).replace(/\s+/g, " ")}`);
  await shot("follow-up");
});

await step("chat survives reload", async () => {
  await page.reload();
  await page.click(".infer-ai-floating-ball");
  await page.fill("#infer-ai-project-search", projectName);
  await page.locator(".infer-ai-project-option", { hasText: projectName }).click();
  await page.locator(".infer-ai-turn").nth(1).waitFor({ timeout: 5_000 });
});

await step("search mode", async () => {
  await page.selectOption(".infer-ai-mode", "STANDARD");
  const before = await page.locator(".infer-ai-turn").count();
  await page.fill(".infer-ai-message-form textarea", "sick leave");
  await page.press(".infer-ai-message-form textarea", "Enter");
  const turn = page.locator(".infer-ai-turn").nth(before);
  await turn.locator(".infer-ai-source").first().waitFor({ timeout: 60_000 });
  await shot("search-mode");
});

// A large text file: indexing it takes long enough to stop it midway.
function bigTextFile(name) {
  const words = "safety ladder exit kit audit report team floor shift supervisor training record".split(" ");
  let seed = name.length;
  const pick = () => words[(seed = (seed * 1103515245 + 12345) % 2147483648) % words.length];
  const lines = [];
  for (let i = 0; i < 25000; i++) lines.push(`${Array.from({ length: 14 }, pick).join(" ")}. Note ${i}.`);
  const file = path.join(os.tmpdir(), name);
  fs.writeFileSync(file, lines.join("\n"));
  return file;
}

async function documentStatus(name) {
  const res = await api(`/upload/documents?project_id=${encodeURIComponent(projectId)}&search=${encodeURIComponent(name)}`);
  return res.body?.data?.documents?.[0]?.indexing_status;
}

await step("stop processing from the assistant", async () => {
  await page.setInputFiles(".infer-ai-message-form input[type=file]", [bigTextFile("e2e_stop_assistant.txt")]);
  const card = page.locator(".infer-ai-upload-item", { hasText: "e2e_stop_assistant.txt" });
  await card.locator(".infer-ai-upload-stop").click({ timeout: 60_000 });
  await card.locator(".infer-ai-upload-status", { hasText: "Stopped" }).waitFor({ timeout: 5_000 });
  await shot("assistant-stopped");
  const status = await documentStatus("e2e_stop_assistant.txt");
  if (status !== "CANCELLED") throw new Error(`backend status ${status}, expected CANCELLED`);
});

await step("project page upload", async () => {
  await page.goto(`${UI}/projects/${encodeURIComponent(projectId)}`);
  await page.setInputFiles("#project-document-files", [path.join(FILES, "inventory.csv")]);
  await page.click(".project-document-upload-button");
  await page.getByText("Upload submitted successfully (1 file(s)).").waitFor({ timeout: 30_000 });
  await page.getByText("inventory.csv").first().waitFor({ timeout: 30_000 });
  await shot("project-upload");
});

await step("stop processing from the project page", async () => {
  await page.setInputFiles("#project-document-files", [bigTextFile("e2e_stop_project.txt")]);
  await page.click(".project-document-upload-button");
  const row = page.locator("tr", { hasText: "e2e_stop_project.txt" });
  // The list follows processing documents on its own; no manual refresh.
  await row.locator(".project-document-stop").click({ timeout: 60_000 });
  await row.locator(".project-document-status", { hasText: "Stopped" }).waitFor({ timeout: 5_000 });
  await shot("project-stopped");
  const status = await documentStatus("e2e_stop_project.txt");
  if (status !== "CANCELLED") throw new Error(`backend status ${status}, expected CANCELLED`);
});

if (projectId) {
  await step("delete project", async () => {
    const res = await api(`/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
    if (res.status >= 300) throw new Error(`HTTP ${res.status}`);
    const after = await api(`/upload/documents?project_id=${encodeURIComponent(projectId)}`);
    const left = after.body?.data?.documents?.length ?? 0;
    if (left) throw new Error(`${left} document(s) still listed after delete`);
  });
}

await browser.close();
log(`done in ${((Date.now() - t0) / 1000).toFixed(0)}s; screenshots in ${SHOTS}`);
if (problems.length) {
  console.log("\nProblems:\n" + problems.map((p) => `- ${p}`).join("\n"));
  process.exit(1);
}
