// The demo page (spec 08 D5, ISS-066). Everything from the server is inserted with textContent,
// never as HTML: an answer can't inject markup or scripts into this page.
"use strict";

const STATUS = {
  answered: "Answered",
  no_answer: "No answer in your documents",
  refused: "Refused",
};

const ERRORS = {
  401: "The token is missing, wrong, or expired. Get a new one with the command above.",
  413: "That question is too long.",
  422: "Please write a question (up to 1,000 characters).",
  503: "The assistant is temporarily unavailable (often a model rate limit). Try again in a minute.",
};

function el(id) {
  return document.getElementById(id);
}

function show(node, visible) {
  node.hidden = !visible;
}

function remember(token) {
  try {
    sessionStorage.setItem("token", token);
  } catch (_) {
    /* private mode: just don't remember it */
  }
}

function recall() {
  try {
    return sessionStorage.getItem("token") || "";
  } catch (_) {
    return "";
  }
}

async function ask(event) {
  event.preventDefault();
  const token = el("token").value.trim();
  const question = el("question").value.trim();
  if (!token || !question) return;
  remember(token);

  const button = el("submit");
  button.disabled = true;
  button.textContent = "Asking…";
  show(el("error"), false);
  const started = performance.now();
  try {
    const response = await fetch("/v1/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) {
      el("error").textContent = ERRORS[response.status] || `Request failed (${response.status}).`;
      show(el("error"), true);
      show(el("result"), false);
      return;
    }
    render(await response.json(), (performance.now() - started) / 1000);
  } catch (_) {
    el("error").textContent = "Couldn't reach the API. Is `docker compose up` running?";
    show(el("error"), true);
  } finally {
    button.disabled = false;
    button.textContent = "Ask";
  }
}

function render(body, seconds) {
  const status = el("status");
  status.textContent = STATUS[body.status] || body.status;
  status.className = `badge ${body.status}`;
  el("elapsed").textContent = `${seconds.toFixed(1)} s`;
  el("answer").textContent = body.answer;
  el("request-id").textContent = body.request_id;

  const list = el("sources");
  list.replaceChildren();
  for (const citation of body.citations) {
    const item = document.createElement("li");
    item.textContent = `${citation.source} — page ${citation.page} (${citation.doc_id})`;
    list.appendChild(item);
  }
  show(el("sources-title"), body.citations.length > 0);
  show(el("result"), true);
}

document.addEventListener("DOMContentLoaded", () => {
  el("token").value = recall();
  el("ask").addEventListener("submit", ask);
  for (const example of el("examples").querySelectorAll("button")) {
    example.addEventListener("click", () => {
      el("question").value = example.textContent;
      el("question").focus();
    });
  }
});
