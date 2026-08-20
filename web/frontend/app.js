// Talks to the synreplace REST API. Served from the same origin by the
// FastAPI backend (see web/backend/app/main.py), so a relative URL is enough;
// point API_BASE elsewhere if you serve this file separately from the API.
const API_BASE = "";

// A fixed, pre-generated 512-word paragraph for quickly trying the tool out
// without needing to paste your own text. Word count isn't recomputed at
// runtime -- it's just a convenient, realistic-length sample.
const SAMPLE_TEXT = `Modern research increasingly depends on collaboration between scientists working across different countries and disciplines. A single discovery rarely emerges from an isolated effort; instead, it typically results from the combined contributions of numerous researchers who share data, exchange ideas, and challenge each other's assumptions. This collaborative spirit has transformed the pace at which important breakthroughs occur, especially within fields such as medicine, physics, and computer science, where problems are often too complex for any individual to solve alone.

Consider the development of a new medical treatment. Before a promising compound ever reaches a patient, it must pass through several demanding stages of investigation. Scientists first examine the molecule in a laboratory setting, carefully measuring its effects on isolated cells. If the results appear encouraging, researchers proceed to test the substance in animal models, observing whether it produces the desired outcome without causing unacceptable harm. Only after these preliminary studies succeed does a treatment advance to clinical trials involving human volunteers, a process that can take years and requires enormous financial investment.

Throughout this journey, teachers and mentors play a crucial role in preparing the next generation of investigators. A skilled instructor does more than transmit information; she teaches students how to formulate meaningful questions, design rigorous experiments, and interpret ambiguous data with appropriate caution. Universities that emphasize this kind of training tend to produce graduates who continue contributing valuable insights long after they leave the classroom.

Government agencies and private companies also shape the direction of scientific progress. Public funding allows researchers to pursue ambitious projects that might otherwise seem too risky for a commercial sponsor, while industry partnerships often accelerate the transition from an interesting discovery to a practical product. When these institutions cooperate effectively, the resulting synergy can produce remarkable achievements that benefit society.

Nevertheless, the path toward genuine understanding is rarely straightforward. Experiments frequently yield surprising or contradictory results, forcing scientists to revise their original hypotheses. A careful researcher treats such setbacks not as failures but as opportunities to refine a theory and design a better experiment. This iterative process, though sometimes frustrating, strengthens the reliability of scientific knowledge and helps prevent flawed conclusions from becoming widely accepted.

Communication remains equally important. A brilliant discovery has limited value if nobody else can understand or replicate it. For this reason, researchers publish detailed reports describing their methods, results, and conclusions, allowing other experts to evaluate the work and attempt to reproduce it independently. This system of peer review, while imperfect, provides an essential safeguard against error and helps maintain public trust in science.

Students entering this field today face extraordinary opportunities and real challenges. Advances in computing power now allow researchers to analyze massive datasets that would have been impossible to process a few decades ago. At the same time, the growing complexity of modern problems demands broader collaboration and a willingness to learn new skills.

Ultimately, the pursuit of knowledge depends on curiosity, patience, and a genuine commitment to honesty. Every researcher shares the same fundamental goal: to understand the world a little better than it was understood before.`;

const els = {
  text: document.getElementById("text"),
  every: document.getElementById("every"),
  slide: document.getElementById("slide"),
  senses: document.getElementById("senses"),
  threshold: document.getElementById("threshold"),
  allowMultiword: document.getElementById("allow_multiword"),
  rewriteBtn: document.getElementById("rewrite-btn"),
  sampleBtn: document.getElementById("sample-btn"),
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

function pasteSampleText() {
  els.text.value = SAMPLE_TEXT;
  els.text.focus();
  hideError();
  setStatus("Sample text pasted.");
  setTimeout(() => setStatus(""), 1500);
}

els.rewriteBtn.addEventListener("click", rewrite);
els.copyBtn.addEventListener("click", copyResult);
els.downloadBtn.addEventListener("click", downloadResult);
els.sampleBtn.addEventListener("click", pasteSampleText);
