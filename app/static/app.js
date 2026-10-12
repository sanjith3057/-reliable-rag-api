// Reliable RAG console. Plain JavaScript, no build step.
// Everything that comes from a document or the model is written with textContent, never innerHTML.

const $ = (selector) => document.querySelector(selector);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

class ApiError extends Error {
  constructor(code, message, requestId) {
    super(message);
    this.code = code;
    this.requestId = requestId;
  }
}

// The API key, if the server requires one, lives only in this tab's session storage.
function apiKey() {
  try { return sessionStorage.getItem("apiKey") || ""; } catch { return ""; }
}

async function api(path, options = {}, isRetry = false) {
  let response;
  const headers = { ...(options.headers || {}) };
  if (apiKey()) headers["X-API-Key"] = apiKey();
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new ApiError("NETWORK_ERROR", "Could not reach the server.");
  }
  const body = await response.json().catch(() => null);
  if (response.status === 401 && !isRetry) {
    const entered = prompt("This server requires an API key:");
    if (entered) {
      try { sessionStorage.setItem("apiKey", entered.trim()); } catch { /* storage unavailable */ }
      return api(path, options, true);
    }
  }
  if (!response.ok) {
    const error = body && body.error;
    throw new ApiError(
      error ? error.code : `HTTP_${response.status}`,
      error ? error.message : "The request failed.",
      error ? error.request_id : undefined,
    );
  }
  return body;
}

const postJson = (path, payload) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });

function toast(message, code, kind = "error") {
  const node = el("div", `toast ${kind === "info" ? "info" : ""}`);
  if (code) node.append(el("span", "toast-code", code));
  node.append(document.createTextNode(message));
  $("#toasts").append(node);
  setTimeout(() => node.remove(), 6000);
}

const showError = (error) => toast(error.message, error.code || "ERROR");

// ── Theme ───────────────────────────────────────────────────────────────
function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch { /* storage unavailable */ }
  if (saved) document.documentElement.dataset.theme = saved;
  $("#theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.dataset.theme
      || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch { /* storage unavailable */ }
  });
}

// ── Health ──────────────────────────────────────────────────────────────
async function refreshHealth() {
  const status = $("#status");
  try {
    const health = await api("/health");
    status.className = "status ok";
    $("#status-text").textContent = "Ready";
    status.title = [
      `Model: ${health.llm.provider} / ${health.llm.model}`,
      `Embeddings: ${health.embedding_model}`,
      `Reranker: ${health.reranker ? "on" : "off"} · BM25: ${health.hybrid ? "on" : "off"}`,
      `Relevance gate: ${health.similarity_threshold}`,
    ].join("\n");
    $("#max-mb").textContent = health.limits.max_file_mb;
    $("#question").maxLength = health.limits.max_question_chars;
    updateCharCount();
  } catch {
    status.className = "status down";
    $("#status-text").textContent = "Offline";
    status.title = "The server could not be reached.";
  }
}

// ── Library ─────────────────────────────────────────────────────────────
// Shown when the bundled samples are loaded: two answerable, one trap the system should refuse.
const SAMPLE_QUESTIONS = [
  "How many days of annual leave do employees get in 2025?",
  "Which scanner has the longer battery life, the Orbit A1 or the Orbit B2?",
  "What is the password for the guest Wi-Fi network?",
];
// Shown for the user's own documents, where we cannot know what is inside.
const STARTER_QUESTIONS = ["Summarise this document", "What are the key points?", "What dates or deadlines are mentioned?"];

async function refreshDocuments() {
  let documents = [];
  try {
    documents = (await api("/documents")).documents;
  } catch (error) {
    showError(error);
    return;
  }
  const list = $("#doc-list");
  list.replaceChildren();
  for (const doc of documents) {
    const item = el("li", "doc");
    item.append(el("span", "doc-kind", doc.doc_name.split(".").pop().toUpperCase().slice(0, 4)));
    const body = el("div", "doc-body");
    const name = el("div", "doc-name", doc.doc_name);
    name.title = doc.doc_name;
    const pages = doc.pages ? ` · ${doc.pages} page${doc.pages === 1 ? "" : "s"}` : "";
    body.append(name, el("div", "doc-meta", `${doc.chunks} chunk${doc.chunks === 1 ? "" : "s"}${pages}`));
    const remove = el("button", "doc-remove", "×");
    remove.type = "button";
    remove.title = `Remove ${doc.doc_name}`;
    remove.setAttribute("aria-label", `Remove ${doc.doc_name}`);
    remove.addEventListener("click", async () => {
      try {
        await api(`/documents/${encodeURIComponent(doc.doc_id)}`, { method: "DELETE" });
        await refreshDocuments();
      } catch (error) {
        showError(error);
      }
    });
    item.append(body, remove);
    list.append(item);
  }
  $("#doc-count").textContent = documents.length;
  $("#doc-empty").hidden = documents.length > 0;
  $("#reset").disabled = documents.length === 0;
  renderSuggestions(documents);
}

function renderSuggestions(documents) {
  const box = $("#suggestions");
  const samplesLoaded = documents.some((doc) => doc.doc_name === "hr_policy_2025.md");
  const questions = samplesLoaded ? SAMPLE_QUESTIONS : documents.length ? STARTER_QUESTIONS : [];
  box.replaceChildren();
  box.hidden = questions.length === 0;
  for (const question of questions) {
    const chip = el("button", "chip", question);
    chip.type = "button";
    chip.addEventListener("click", () => {
      $("#question").value = question;
      updateCharCount();
      ask();
    });
    box.append(chip);
  }
}

async function uploadFiles(files) {
  const dropzone = $("#dropzone");
  dropzone.classList.add("busy");
  for (const file of files) {
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await api("/ingest", { method: "POST", body: form });
      toast(`${result.doc_name}: ${result.chunks} chunks (${result.status})`, "INGESTED", "info");
    } catch (error) {
      toast(`${file.name}: ${error.message}`, error.code);
    }
  }
  dropzone.classList.remove("busy");
  $("#file-input").value = "";
  await refreshDocuments();
}

function initLibrary() {
  const dropzone = $("#dropzone");
  $("#file-input").addEventListener("change", (event) => uploadFiles([...event.target.files]));
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      $("#file-input").click();
    }
  });
  for (const type of ["dragenter", "dragover"]) {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragging");
    });
  }
  for (const type of ["dragleave", "drop"]) {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragging");
    });
  }
  dropzone.addEventListener("drop", (event) => uploadFiles([...event.dataTransfer.files]));

  $("#load-samples").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Loading…";
    try {
      const ingested = await api("/ingest/samples", { method: "POST" });
      toast(`${ingested.length} sample documents ready`, "INGESTED", "info");
    } catch (error) {
      showError(error);
    }
    button.disabled = false;
    button.textContent = "Load sample docs";
    await refreshDocuments();
    refreshHealth();
  });

  $("#reset").addEventListener("click", async () => {
    if (!confirm("Remove every document from the library?")) return;
    try {
      await api("/reset", { method: "POST" });
    } catch (error) {
      showError(error);
    }
    await refreshDocuments();
  });
}

// ── Ask ─────────────────────────────────────────────────────────────────
const ABSTAIN_REASONS = {
  below_threshold: "Nothing in the library was close enough to this question, so no answer was generated.",
  model_abstained: "Related passages were found, but none of them state the answer.",
  no_valid_citations: "An answer was drafted, but it could not be tied to a retrieved passage, so it was withheld.",
};

// The counter only appears when the question is getting close to the limit.
function updateCharCount() {
  const input = $("#question");
  const counter = $("#char-count");
  counter.hidden = input.value.length < input.maxLength * 0.8;
  counter.textContent = `${input.value.length} / ${input.maxLength}`;
}

function answerCard(question) {
  const card = el("article", "answer pending");
  const head = el("div", "answer-head");
  const badge = el("span", "badge", "Thinking…");
  head.append(el("div", "answer-question", question), badge);
  const body = el("div");
  body.append(el("div", "skeleton"), el("div", "skeleton short"));
  card.append(head, body);
  return { card, badge, body };
}

function renderSource(source) {
  const node = el("div", "source");
  const head = el("div", "source-head");
  head.append(el("span", "source-name", source.doc_name));
  if (source.page) head.append(el("span", "source-page", `p. ${source.page}`));
  const meter = el("span", "meter");
  meter.title = "Cosine similarity between your question and this passage";
  const track = el("span", "meter-track");
  const fill = el("span", "meter-fill");
  fill.style.width = `${Math.max(0, Math.min(1, source.score)) * 100}%`;
  track.append(fill);
  meter.append(track, document.createTextNode(source.score.toFixed(2)));
  head.append(meter);
  node.append(head, el("blockquote", "", source.excerpt));
  return node;
}

async function ask() {
  const input = $("#question");
  const question = input.value.trim();
  if (!question) {
    input.focus();
    return;
  }
  const button = $("#ask-button");
  button.disabled = true;
  $("#ask-empty").hidden = true;
  const { card, badge, body } = answerCard(question);
  $("#answers").prepend(card);

  try {
    const result = await postJson("/ask", { question });
    body.replaceChildren();
    if (result.answerable) {
      card.className = "answer";
      const count = result.sources.length;
      badge.textContent = `Grounded · ${count} source${count === 1 ? "" : "s"}`;
      body.append(el("div", "answer-text", result.answer));
      const sources = el("div", "sources");
      sources.append(el("div", "sources-title", "Evidence"));
      const list = el("div", "source-list");
      result.sources.forEach((source) => list.append(renderSource(source)));
      sources.append(list);
      body.append(sources);
    } else {
      card.className = "answer abstained";
      badge.textContent = "Not in your documents";
      body.append(el("div", "answer-text", result.answer));
      body.append(el("div", "answer-why", ABSTAIN_REASONS[result.abstain_reason] || ""));
    }
    input.value = "";
    updateCharCount();
  } catch (error) {
    card.className = "answer failed";
    badge.textContent = error.code || "Error";
    body.replaceChildren(el("div", "answer-text", error.message));
    if (error.requestId) body.append(el("div", "answer-why", `Request ID: ${error.requestId}`));
  }
  button.disabled = false;
}

function initAsk() {
  $("#ask-form").addEventListener("submit", (event) => {
    event.preventDefault();
    ask();
  });
  $("#question").addEventListener("input", updateCharCount);
  $("#question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      ask();
    }
  });
}

// ── Evaluate ────────────────────────────────────────────────────────────
const METRICS = [
  ["retrieval_hit_at_k", "Retrieval hit@k"],
  ["abstention_accuracy", "Abstention accuracy"],
  ["citation_correctness", "Citation correctness"],
  ["answer_keyword_accuracy", "Answer accuracy"],
  ["distractor_resilience", "Distractor resilience"],
];

function tile(label, value, fraction) {
  const node = el("div", "tile");
  node.append(el("div", "tile-label", label), el("div", "tile-value", value));
  if (fraction !== null && fraction !== undefined) {
    if (fraction < 0.8) node.classList.add("low");
    const bar = el("div", "tile-bar");
    const fill = el("span");
    fill.style.width = `${fraction * 100}%`;
    bar.append(fill);
    node.append(bar);
  }
  return node;
}

function renderReport(report) {
  $("#eval-empty").hidden = true;
  const summary = report.summary;
  const config = report.config;
  $("#eval-meta").textContent =
    `${report.dataset} set · ${report.run_id} · ${config.llm} · k=${config.top_k} · gate ${config.similarity_threshold}`
    + `${config.hybrid ? " · hybrid" : ""}${config.reranker ? " · reranker" : ""}`;

  const tiles = $("#eval-tiles");
  tiles.replaceChildren(tile("Questions passed", `${summary.passed} / ${summary.total}`, summary.total ? summary.passed / summary.total : null));
  for (const [key, label] of METRICS) {
    const value = summary[key];
    tiles.append(tile(label, value === null ? "n/a" : `${Math.round(value * 100)}%`, value));
  }
  tiles.append(tile("Average latency", `${Math.round(summary.avg_latency_ms)} ms`, null));

  const rows = $("#eval-table tbody");
  rows.replaceChildren();
  for (const result of report.results) {
    const row = el("tr");
    const verdict = el("td");
    verdict.append(el("span", `pill ${result.passed ? "pass" : "fail"}`, result.passed ? "pass" : "fail"));
    const got = result.error ? result.error : result.answerable ? "answered" : "abstained";
    const question = el("td", "question", result.question);
    if (result.answer) question.title = result.answer;
    row.append(
      el("td", "mono", result.id),
      el("td", "mono", result.type),
      verdict,
      question,
      el("td", "mono", result.expected_answerable ? "answer" : "abstain"),
      el("td", "mono", got),
      el("td", "mono", result.cited.join(", ") || "–"),
      el("td", "num", `${Math.round(result.latency_ms)} ms`),
    );
    rows.append(row);
  }
  $("#eval-table").hidden = false;
}

async function loadLatestReport() {
  try {
    renderReport(await api("/eval/latest"));
  } catch {
    // No run yet; the empty note already says so.
  }
}

function initEval() {
  $("#run-eval").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Running…";
    try {
      renderReport(await postJson("/eval", { dataset: $("#dataset").value }));
    } catch (error) {
      showError(error);
    }
    button.disabled = false;
    button.textContent = "Run evaluation";
  });
}

// ── Tabs ────────────────────────────────────────────────────────────────
function initTabs() {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".tab")) {
        const active = other === tab;
        other.classList.toggle("active", active);
        other.setAttribute("aria-selected", String(active));
        $(`#tab-${other.dataset.tab}`).hidden = !active;
      }
      if (tab.dataset.tab === "eval" && $("#eval-table").hidden) loadLatestReport();
    });
  }
}

initTheme();
initTabs();
initLibrary();
initAsk();
initEval();
refreshHealth();
refreshDocuments();
