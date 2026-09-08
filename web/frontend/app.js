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
  senses: document.getElementById("senses"),
  threshold: document.getElementById("threshold"),
  thresholdValue: document.getElementById("threshold-value"),
  slideToggle: document.getElementById("slide-toggle"),
  multiwordToggle: document.getElementById("multiword-toggle"),
  sourcesBtn: document.getElementById("sources-btn"),
  sourcesSummary: document.getElementById("sources-summary"),
  sourcesPanel: document.getElementById("sources-panel"),
  sourceCheckboxes: document.querySelectorAll(".source-checkbox"),
  ribbonKeys: document.querySelectorAll("#ribbon-keys .key"),
  rewriteBtn: document.getElementById("rewrite-btn"),
  rewriteLabel: document.getElementById("rewrite-label"),
  loadingBar: document.getElementById("loading-bar"),
  sampleBtn: document.getElementById("sample-btn"),
  status: document.getElementById("status"),
  pageResult: document.getElementById("page-result"),
  viewBlack: document.getElementById("view-black"),
  viewBlackRed: document.getElementById("view-blackred"),
  viewDuplicate: document.getElementById("view-duplicate"),
  galleyOriginalText: document.querySelector("#galley-original .galley-text"),
  galleySetText: document.querySelector("#galley-set .galley-text"),
  gutter: document.getElementById("gutter"),
  correctionsPanel: document.getElementById("corrections-panel"),
  correctionsHeading: document.getElementById("corrections-heading"),
  cardsRow: document.getElementById("cards-row"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),
  errorPanel: document.getElementById("error-panel"),
  errorMessage: document.getElementById("error-message"),
};

// The last rewrite response's full token list (words + the gaps between
// them), kept client-side so a Reset/alternative click can edit one word and
// rebuild every view without re-implementing word-boundary detection --
// mirrors the API's `tokens` field 1:1. See web/docs/API.md.
let currentTokens = [];

// position -> the word that was originally there, for every position the API
// actually replaced. Fixed for the life of one rewrite response; only
// currentTokens changes as the user resets/picks alternatives. Drives the
// struck-through text in Black+Red and the "Original" galley in Duplicate.
let originalByPosition = new Map();

// "black" | "blackred" | "duplicate"
let currentMode = "black";

// The <span class="result-word"> currently highlighted by jumpToWord(), if any.
let highlightedWord = null;

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
  els.rewriteLabel.textContent = isBusy ? "Striking…" : "Strike";
  els.loadingBar.hidden = !isBusy;
}

function showError(message) {
  els.errorPanel.hidden = false;
  els.errorMessage.textContent = message;
  els.pageResult.hidden = true;
  els.correctionsPanel.hidden = true;
}

function hideError() {
  els.errorPanel.hidden = true;
}

function similarityLabel(similarity) {
  return similarity == null ? "—" : Math.round(similarity * 100) + "%";
}

function currentResultText() {
  return currentTokens.map((t) => t.text).join("");
}

// ============================= result views =============================
// Three renderings of the same currentTokens, kept in sync and switched
// between with [hidden] by the ribbon selector -- see setMode(). Rebuilding
// all three from scratch on every edit (rather than patching spans in place)
// keeps them from drifting out of sync with each other; at a few hundred
// words this is cheap.

function renderAllViews() {
  renderPlainView(els.viewBlack, currentTokens);
  renderCorrectionView(els.viewBlackRed);
  renderDuplicateView();
  if (currentMode === "duplicate") computeGutterMarks();
}

function wordSpan(text, position, extraClass) {
  const span = document.createElement("span");
  span.className = "result-word" + (extraClass ? " " + extraClass : "");
  span.dataset.position = position;
  span.textContent = text;
  return span;
}

// Renders a token list as plain text, one <span class="result-word"> per
// word so a specific word can later get a real, persistent highlight --
// see jumpToWord().
function renderPlainView(container, tokens) {
  container.innerHTML = "";
  for (const token of tokens) {
    if (token.is_word) {
      container.appendChild(wordSpan(token.text, token.position, null));
    } else {
      container.appendChild(document.createTextNode(token.text));
    }
  }
}

// Same text, but a word that no longer matches its original gets the
// original struck through in front of it -- "old word crossed and the new
// word next to it".
function renderCorrectionView(container) {
  container.innerHTML = "";
  for (const token of currentTokens) {
    if (!token.is_word) {
      container.appendChild(document.createTextNode(token.text));
      continue;
    }
    const original = originalByPosition.get(token.position);
    if (original !== undefined && original !== token.text) {
      const s = document.createElement("s");
      s.className = "struck";
      s.textContent = original;
      container.appendChild(s);
      container.appendChild(document.createTextNode(" "));
      container.appendChild(wordSpan(token.text, token.position, "corr"));
    } else {
      container.appendChild(wordSpan(token.text, token.position, null));
    }
  }
}

// Two galleys side by side: the untouched original text on the left, the
// current text on the right with changed words picked out in red -- the
// pairing is drawn as marks in the gutter between them, see computeGutterMarks().
function renderDuplicateView() {
  els.galleyOriginalText.innerHTML = "";
  for (const token of currentTokens) {
    if (!token.is_word) {
      els.galleyOriginalText.appendChild(document.createTextNode(token.text));
      continue;
    }
    const original = originalByPosition.get(token.position);
    els.galleyOriginalText.appendChild(document.createTextNode(original !== undefined ? original : token.text));
  }
  renderPlainViewWithCorrections(els.galleySetText);
}

function renderPlainViewWithCorrections(container) {
  container.innerHTML = "";
  for (const token of currentTokens) {
    if (!token.is_word) {
      container.appendChild(document.createTextNode(token.text));
      continue;
    }
    const original = originalByPosition.get(token.position);
    const changed = original !== undefined && original !== token.text;
    container.appendChild(wordSpan(token.text, token.position, changed ? "corr" : null));
  }
}

// Places a small mark in the gutter at the vertical center of every changed
// word in the "Set" galley -- run only while the Duplicate view is actually
// visible, since a hidden element has no layout to measure.
function computeGutterMarks() {
  els.gutter.innerHTML = "";
  const gutterRect = els.gutter.getBoundingClientRect();
  for (const token of currentTokens) {
    if (!token.is_word) continue;
    const original = originalByPosition.get(token.position);
    if (original === undefined || original === token.text) continue;
    const span = els.galleySetText.querySelector('.result-word[data-position="' + token.position + '"]');
    if (!span) continue;
    const rect = span.getBoundingClientRect();
    const mark = document.createElement("span");
    mark.className = "mark";
    mark.setAttribute("aria-hidden", "true");
    mark.textContent = "⌐";
    mark.style.top = (rect.top - gutterRect.top + rect.height / 2) + "px";
    els.gutter.appendChild(mark);
  }
}

let gutterResizeTimer = null;
window.addEventListener("resize", () => {
  if (currentMode !== "duplicate" || els.pageResult.hidden) return;
  clearTimeout(gutterResizeTimer);
  gutterResizeTimer = setTimeout(computeGutterMarks, 150);
});

function setMode(mode) {
  currentMode = mode;
  els.viewBlack.hidden = mode !== "black";
  els.viewBlackRed.hidden = mode !== "blackred";
  els.viewDuplicate.hidden = mode !== "duplicate";
  for (const key of els.ribbonKeys) {
    const active = key.dataset.mode === mode;
    key.classList.toggle("active", active);
    key.setAttribute("aria-checked", active ? "true" : "false");
  }
  if (highlightedWord) {
    highlightedWord.classList.remove("highlight");
    highlightedWord = null;
  }
  if (mode === "duplicate") computeGutterMarks();
}

function activeViewContainer() {
  if (currentMode === "black") return els.viewBlack;
  if (currentMode === "blackred") return els.viewBlackRed;
  return els.galleySetText;
}

function resultWordSpan(position) {
  return activeViewContainer().querySelector('.result-word[data-position="' + position + '"]');
}

// Gives that word's span in the currently active view a real, persistent
// highlight (clearing any previous one) and scrolls it to the center of the
// page -- more visible and more reliable than a native text selection, which
// is easy to lose among 500 words and disappears the moment focus moves on.
function jumpToWord(position) {
  const span = resultWordSpan(position);
  if (!span) return;
  if (highlightedWord) highlightedWord.classList.remove("highlight");
  span.classList.add("highlight");
  highlightedWord = span;
  span.scrollIntoView({ behavior: "smooth", block: "center" });
}

// ============================= corrections cards =============================

function renderResult(data) {
  els.pageResult.hidden = false;
  els.correctionsPanel.hidden = false;
  currentTokens = data.tokens.map((t) => ({ ...t }));
  originalByPosition = new Map(data.replacements.map((r) => [r.position, r.original]));
  highlightedWord = null;
  renderAllViews();

  els.correctionsHeading.textContent =
    data.substitution_count + " correction" + (data.substitution_count === 1 ? "" : "s");

  els.cardsRow.innerHTML = "";
  for (const item of data.replacements) {
    els.cardsRow.appendChild(buildCard(item));
  }
}

function buildCard(item) {
  const card = document.createElement("div");
  card.className = "idx-card";
  card.dataset.position = item.position;

  const words = document.createElement("div");
  words.className = "words";
  const originalSpan = document.createElement("span");
  originalSpan.className = "word-original";
  originalSpan.textContent = item.original + " →";
  const wordLink = document.createElement("button");
  wordLink.type = "button";
  wordLink.className = "word-link";
  wordLink.textContent = item.replacement;
  wordLink.title = "Find this word in the page";
  wordLink.addEventListener("click", () => jumpToWord(item.position));
  const sim = document.createElement("span");
  sim.className = "sim";
  sim.textContent = similarityLabel(item.similarity);
  words.appendChild(originalSpan);
  words.appendChild(wordLink);
  words.appendChild(sim);
  card.appendChild(words);

  const altsRow = document.createElement("div");
  altsRow.className = "alts";
  const chips = [];
  for (const alt of item.alternatives) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "alt-chip";
    chip.textContent = alt.word + " " + similarityLabel(alt.similarity);
    chip.addEventListener("click", () => applyChoice(card, item, alt.word, alt.similarity, chip, chips));
    chips.push(chip);
    altsRow.appendChild(chip);
  }
  if (item.alternatives.length > 0) card.appendChild(altsRow);

  const resetBtn = document.createElement("button");
  resetBtn.type = "button";
  resetBtn.className = "reset-link";
  resetBtn.textContent = "Reset";
  resetBtn.addEventListener("click", () => applyChoice(card, item, item.original, null, null, chips));
  card.appendChild(resetBtn);

  return card;
}

// Sets `word` as the currently-applied text at `item.position`, re-renders
// every view from the updated tokens, and updates this card's own display.
function applyChoice(card, item, word, similarity, activeChip, allChips) {
  const token = currentTokens.find((t) => t.is_word && t.position === item.position);
  if (token) token.text = word;
  renderAllViews();

  card.querySelector(".word-link").textContent = word;
  card.querySelector(".sim").textContent = similarityLabel(similarity);
  card.classList.toggle("is-reset", word === item.original);
  for (const chip of allChips) chip.classList.toggle("active", chip === activeChip);
}

// ============================= sources popover =============================

function checkedSources() {
  return Array.from(els.sourceCheckboxes)
    .filter((checkbox) => checkbox.checked)
    .map((checkbox) => checkbox.value);
}

function updateSourcesSummary() {
  const checked = checkedSources();
  if (checked.length === 0) {
    els.sourcesSummary.textContent = "none";
  } else if (checked.length === 1) {
    els.sourcesSummary.textContent = checked[0];
  } else {
    els.sourcesSummary.textContent = checked[0] + " +" + (checked.length - 1);
  }
}

els.sourcesBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  const isOpen = !els.sourcesPanel.hidden;
  els.sourcesPanel.hidden = isOpen;
  els.sourcesBtn.setAttribute("aria-expanded", String(!isOpen));
});
document.addEventListener("click", (event) => {
  if (els.sourcesPanel.hidden) return;
  if (els.sourcesPanel.contains(event.target) || els.sourcesBtn.contains(event.target)) return;
  els.sourcesPanel.hidden = true;
  els.sourcesBtn.setAttribute("aria-expanded", "false");
});
for (const checkbox of els.sourceCheckboxes) {
  checkbox.addEventListener("change", updateSourcesSummary);
}

// ============================= toggles =============================

function bindToggle(button) {
  button.addEventListener("click", () => {
    const pressed = button.getAttribute("aria-pressed") === "true";
    button.setAttribute("aria-pressed", String(!pressed));
  });
}
bindToggle(els.slideToggle);
bindToggle(els.multiwordToggle);

for (const key of els.ribbonKeys) {
  key.addEventListener("click", () => setMode(key.dataset.mode));
}

// ============================= rewrite =============================

async function rewrite() {
  const text = els.text.value;
  if (!text.trim()) {
    showError("Enter some text first.");
    return;
  }
  const sources = checkedSources();
  if (sources.length === 0) {
    showError("Pick at least one source.");
    return;
  }

  hideError();
  setBusy(true);
  const usesOnlineSource = sources.some((name) => name !== "wordnet");
  setStatus(usesOnlineSource ? "Striking… (online sources can take a while)" : "Striking…");

  const payload = {
    text: text,
    every: Number(els.every.value) || 5,
    slide: els.slideToggle.getAttribute("aria-pressed") === "true",
    senses: Number(els.senses.value) || 3,
    threshold: Number(els.threshold.value),
    allow_multiword: els.multiwordToggle.getAttribute("aria-pressed") === "true",
    sources: sources,
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
    await navigator.clipboard.writeText(currentResultText());
    setStatus("Copied to clipboard.");
    setTimeout(() => setStatus(""), 1500);
  } catch (err) {
    setStatus("Could not copy: " + err.message);
  }
}

function downloadResult() {
  const blob = new Blob([currentResultText()], { type: "text/plain;charset=utf-8" });
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
