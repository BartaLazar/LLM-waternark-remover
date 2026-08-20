// Talks to the synreplace REST API. Served from the same origin by the
// FastAPI backend (see web/backend/app/main.py), so a relative URL is enough;
// point API_BASE elsewhere if you serve this file separately from the API.
const API_BASE = "";

const els = {
  text: document.getElementById("text"),
  every: document.getElementById("every"),
  slide: document.getElementById("slide"),
  senses: document.getElementById("senses"),
  threshold: document.getElementById("threshold"),
  allowMultiword: document.getElementById("allow_multiword"),
  rewriteBtn: document.getElementById("rewrite-btn"),
  status: document.getElementById("status"),
  resultPanel: document.getElementById("result-panel"),
  result: document.getElementById("result"),
  substitutionsHeading: document.getElementById("substitutions-heading"),
  substitutionsBody: document.querySelector("#substitutions tbody"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),
  errorPanel: document.getElementById("error-panel"),
  errorMessage: document.getElementById("error-message"),
};

function setStatus(message) {
  els.status.textContent = message;
}

function showError(message) {
  els.errorPanel.hidden = false;
  els.errorMessage.textContent = message;
  els.resultPanel.hidden = true;
}

function hideError() {
  els.errorPanel.hidden = true;
}

function renderResult(data) {
  els.resultPanel.hidden = false;
  els.result.value = data.result;
  els.substitutionsHeading.textContent =
    data.substitution_count + " substitution" + (data.substitution_count === 1 ? "" : "s");

  els.substitutionsBody.innerHTML = "";
  for (const item of data.replacements) {
    const row = document.createElement("tr");
    const similarityPct = Math.round(item.similarity * 100) + "%";
    row.innerHTML =
      "<td>" + item.position + "</td>" +
      "<td>" + escapeHtml(item.original) + "</td>" +
      "<td>" + escapeHtml(item.replacement) + "</td>" +
      "<td>" + similarityPct + "</td>";
    els.substitutionsBody.appendChild(row);
  }
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

async function rewrite() {
  const text = els.text.value;
  if (!text.trim()) {
    showError("Enter some text first.");
    return;
  }

  hideError();
  els.rewriteBtn.disabled = true;
  setStatus("Rewriting…");

  const payload = {
    text: text,
    every: Number(els.every.value) || 5,
    slide: els.slide.checked,
    senses: Number(els.senses.value) || 1,
    threshold: Number(els.threshold.value),
    allow_multiword: els.allowMultiword.checked,
  };

  try {
    const response = await fetch(API_BASE + "/api/v1/rewrite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const message = body && body.detail
        ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail))
        : ("Request failed with status " + response.status);
      showError(message);
      return;
    }

    const data = await response.json();
    renderResult(data);
  } catch (err) {
    showError("Could not reach the API: " + err.message);
  } finally {
    els.rewriteBtn.disabled = false;
    setStatus("");
  }
}

async function copyResult() {
  try {
    await navigator.clipboard.writeText(els.result.value);
    setStatus("Copied to clipboard.");
    setTimeout(() => setStatus(""), 1500);
  } catch (err) {
    setStatus("Could not copy: " + err.message);
  }
}

function downloadResult() {
  const blob = new Blob([els.result.value], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "synreplace-result.txt";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

els.rewriteBtn.addEventListener("click", rewrite);
els.copyBtn.addEventListener("click", copyResult);
els.downloadBtn.addEventListener("click", downloadResult);
