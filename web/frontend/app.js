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
  wordCount: document.getElementById("word-count"),
  every: document.getElementById("every"),
  slide: document.getElementById("slide"),
  senses: document.getElementById("senses"),
  threshold: document.getElementById("threshold"),
  thresholdValue: document.getElementById("threshold-value"),
  allowMultiword: document.getElementById("allow_multiword"),
  rewriteBtn: document.getElementById("rewrite-btn"),
  rewriteIcon: document.getElementById("rewrite-icon"),
  rewriteSpinner: document.getElementById("rewrite-spinner"),
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

// The last rewrite response's full token list (words + the gaps between
// them), kept client-side so a Reset/alternative click can edit one word and
// rebuild the result text without re-implementing word-boundary detection --
// mirrors the API's `tokens` field 1:1. See web/docs/API.md.
let currentTokens = [];

function setStatus(message) {
  els.status.textContent = message;
}

function updateWordCount() {
  const words = els.text.value.trim().split(/\s+/).filter(Boolean);
  const count = words.length;
  els.wordCount.textContent = count + " word" + (count === 1 ? "" : "s");
}

function setBusy(isBusy) {
  els.rewriteBtn.disabled = isBusy;
  els.rewriteSpinner.hidden = !isBusy;
  els.rewriteIcon.hidden = isBusy;
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
  currentTokens = data.tokens.map((t) => ({ ...t }));
  els.result.value = data.result;
  els.substitutionsHeading.textContent =
    data.substitution_count + " substitution" + (data.substitution_count === 1 ? "" : "s");

  els.substitutionsBody.innerHTML = "";
  for (const item of data.replacements) {
    els.substitutionsBody.appendChild(buildSubstitutionRow(item));
  }
}

function similarityLabel(similarity) {
  return similarity == null ? "—" : Math.round(similarity * 100) + "%";
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

// One row per substitution: the original word, the word currently applied at
// that position (editable via the buttons below), its similarity, up to
// ALTERNATIVES_LIMIT alternative-synonym chips, and a Reset-to-original button.
function buildSubstitutionRow(item) {
  const row = document.createElement("tr");
  row.dataset.position = item.position;

  const currentCell = cell(item.replacement);
  currentCell.className = "current-cell";
  const similarityCell = cell(similarityLabel(item.similarity));
  similarityCell.className = "similarity-cell";

  row.appendChild(cell(String(item.position)));
  row.appendChild(cell(item.original));
  row.appendChild(currentCell);
  row.appendChild(similarityCell);

  const altCell = document.createElement("td");
  altCell.className = "alternatives-cell";
  const chips = [];
  if (item.alternatives.length === 0) {
    // A td with no content at all doesn't establish a normal text baseline,
    // so `vertical-align: baseline` computes a slightly different (shorter)
    // row height for it than for a sibling row whose alternatives cell holds
    // a real chip -- rows drift out of alignment by a pixel or two. An
    // invisible placeholder with the exact same tag (a <button>, not a
    // <span> -- a plain span is inline by default and its vertical padding
    // doesn't expand the line box the way a button's does) has identical box
    // metrics to a real chip, so every row's baseline math matches
    // regardless of whether it has alternatives to show.
    const placeholder = document.createElement("button");
    placeholder.type = "button";
    placeholder.className = "chip chip-placeholder";
    placeholder.textContent = "—";
    placeholder.disabled = true;
    placeholder.setAttribute("aria-hidden", "true");
    altCell.appendChild(placeholder);
  }
  for (const alt of item.alternatives) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = alt.word + " " + similarityLabel(alt.similarity);
    chip.addEventListener("click", () => applyChoice(row, item, alt.word, alt.similarity, chip, chips));
    chips.push(chip);
    altCell.appendChild(chip);
  }
  row.appendChild(altCell);

  const actionCell = document.createElement("td");
  const resetBtn = document.createElement("button");
  resetBtn.type = "button";
  resetBtn.className = "secondary reset-btn";
  resetBtn.title = "Reset to the original word";
  resetBtn.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" class="icon">' +
    '<path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5" /></svg>Reset';
  resetBtn.addEventListener("click", () => applyChoice(row, item, item.original, null, null, chips));
  actionCell.appendChild(resetBtn);
  row.appendChild(actionCell);

  return row;
}

// Sets `word` as the currently-applied text at `item.position`, rebuilds the
// result textarea from the (mutated) token list, and updates this row's
// "Current"/"Similarity" cells and which chip (if any) is marked active.
function applyChoice(row, item, word, similarity, activeChip, allChips) {
  const token = currentTokens.find((t) => t.is_word && t.position === item.position);
  if (token) token.text = word;
  els.result.value = currentTokens.map((t) => t.text).join("");

  row.querySelector(".current-cell").textContent = word;
  row.querySelector(".similarity-cell").textContent = similarityLabel(similarity);
  row.classList.toggle("is-reset", word === item.original);
  for (const chip of allChips) chip.classList.toggle("active", chip === activeChip);
}

async function rewrite() {
  const text = els.text.value;
  if (!text.trim()) {
    showError("Enter some text first.");
    return;
  }

  hideError();
  setBusy(true);
  setStatus("Rewriting…");

  const payload = {
    text: text,
    every: Number(els.every.value) || 5,
    slide: els.slide.checked,
    senses: Number(els.senses.value) || 3,
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
    setBusy(false);
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
  updateWordCount();
  hideError();
  setStatus("Sample text pasted.");
  setTimeout(() => setStatus(""), 1500);
}

els.rewriteBtn.addEventListener("click", rewrite);
els.copyBtn.addEventListener("click", copyResult);
els.downloadBtn.addEventListener("click", downloadResult);
els.sampleBtn.addEventListener("click", pasteSampleText);
els.text.addEventListener("input", updateWordCount);
els.threshold.addEventListener("input", () => {
  els.thresholdValue.textContent = Number(els.threshold.value).toFixed(2);
});

updateWordCount();
