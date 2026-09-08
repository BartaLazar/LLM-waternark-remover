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
  galleysGrid: document.getElementById("galleys-grid"),
  correctionsPanel: document.getElementById("corrections-panel"),
  correctionsHeading: document.getElementById("corrections-heading"),
  cardsRow: document.getElementById("cards-row"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),
  errorPanel: document.getElementById("error-panel"),
  errorMessage: document.getElementById("error-message"),
  helpBtn: document.getElementById("help-btn"),
  helpOverlay: document.getElementById("help-overlay"),
  helpClose: document.getElementById("help-close"),
};

// The last rewrite response's full token list (words + the gaps between
// them), kept client-side so a Reset/alternative click can edit one word and
// rebuild every view without re-implementing word-boundary detection --
// mirrors the API's `tokens` field 1:1. See web/docs/API.md.
let currentTokens = [];

// position -> the word that was originally there, for every position that's
// EVER different from its original -- both an actual substitution (from
// data.replacements) and a word the server or a client-side edit silently
// changed as a side effect of one (currently just "a"/"an" agreement, see
// data.tokens[i].original). Used to reconstruct the true "Original" galley
// in Duplicate, and, for `correctionPositions` below, which of those get the
// struck-through/red "corr" treatment.
let originalByPosition = new Map();

// Positions with a real correction card -- a subset of originalByPosition's
// keys. Only these get the struck-through/red "corr" span (and its click
// handler) in Black+Red and the Duplicate "Set" galley: a silent side-effect
// like an "a"/"an" fix has no card to jump to or highlight.
let correctionPositions = new Set();

// "black" | "blackred" | "duplicate"
let currentMode = "black";

// The <span class="result-word"> currently highlighted by jumpToWord(), if any.
let highlightedWord = null;

// The <div class="idx-card"> currently highlighted by jumpToCard(), if any.
let highlightedCard = null;

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
  // A "corr" span is a replaced word shown in Blk+Red or Duplicate -- clicking
  // it jumps to (and highlights) its card instead of highlighting itself, the
  // reverse of a card's word-link. See jumpToCard().
  if (extraClass === "corr") {
    span.addEventListener("click", () => jumpToCard(position));
  }
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
    if (correctionPositions.has(token.position) && original !== token.text) {
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

// A gap token containing a blank line -- paragraphs are still kept as their
// own visual unit (a divider after each one, see renderDuplicateView()),
// even though the actual alignment grid now cuts far more often than that.
const PARAGRAPH_BREAK_RE = /\n[ \t]*\n/;

function splitIntoParagraphs(tokens) {
  const paragraphs = [];
  let current = [];
  for (const token of tokens) {
    current.push(token);
    if (!token.is_word && PARAGRAPH_BREAK_RE.test(token.text)) {
      paragraphs.push(current);
      current = [];
    }
  }
  if (current.length) paragraphs.push(current);
  return paragraphs;
}

// Cuts one paragraph's tokens into line-sized rows, greedily adding whole
// words until *either* column's text for the row would reach `charsPerLine`
// -- so a row is sized to whichever of the two variants for it is longer,
// and both normally fit on one real line at the column's actual width. This
// is what keeps every row aligned, not just paragraph starts: two
// independently word-wrapped columns drift line by line as soon as a
// replacement is a different length than the original, but a row built this
// way can only ever break at the same word position in both.
function splitParagraphIntoLines(tokens, charsPerLine) {
  const lines = [];
  let current = [];
  let originalLen = 0;
  let setLen = 0;
  for (const token of tokens) {
    let addOriginal, addSet;
    if (token.is_word) {
      const original = originalByPosition.get(token.position);
      addOriginal = (original !== undefined ? original : token.text).length;
      addSet = token.text.length;
    } else {
      addOriginal = addSet = token.text.length;
    }
    // Decide *before* adding a word (never a gap, so a break always lands
    // between words, on the gap that was already appended) whether it would
    // push either column past budget -- checking after the fact, like a
    // running total, lets one long word push a row well past its budget
    // before the next check point even fires.
    if (token.is_word && current.length > 0 &&
        (originalLen + addOriginal > charsPerLine || setLen + addSet > charsPerLine)) {
      lines.push(current);
      current = [];
      originalLen = 0;
      setLen = 0;
    }
    current.push(token);
    originalLen += addOriginal;
    setLen += addSet;
  }
  if (current.length) lines.push(current);
  return lines;
}

// How many monospace characters fit across one text column, measured from
// the actual rendered width (the page frame's, which is laid out regardless
// of which ribbon view is currently visible) and the .gcell class's real
// font -- not guessed, so this stays correct across window sizes and if the
// CSS's font/column widths ever change.
function computeCharsPerLine() {
  const frame = document.querySelector(".page-frame");
  const frameWidth = frame ? frame.getBoundingClientRect().width : 0;
  if (!frame || frameWidth <= 0) return 60; // not laid out yet -- a sane fallback
  const style = getComputedStyle(frame);
  const innerWidth = frameWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const gutterWidth = 26; // matches .result-galleys' grid-template-columns
  const columnWidth = (innerWidth - gutterWidth) / 2;

  const probe = document.createElement("span");
  probe.className = "gcell";
  probe.style.cssText = "position:absolute; visibility:hidden; white-space:pre; left:-9999px; top:0;";
  probe.textContent = "0".repeat(40);
  document.body.appendChild(probe);
  const charWidth = probe.getBoundingClientRect().width / 40;
  document.body.removeChild(probe);

  // A couple of characters of slack: text-node/span boundaries and
  // sub-pixel rounding can make the real rendered width a hair different
  // from charWidth * charCount, so budget slightly under the exact fit
  // rather than risk tipping a row onto a second real line.
  return charWidth > 0 ? Math.max(20, Math.floor(columnWidth / charWidth) - 2) : 58;
}

// Builds the Duplicate view's grid: an "Original" cell and a "Set" cell per
// row, both built from the exact same token slice (see
// splitParagraphIntoLines()), with a gutter cell between them for
// computeGutterMarks(). All three are appended straight into the
// #galleys-grid CSS grid, which auto-places every 3 children into one grid
// row and sizes that row to whichever cell is taller -- no per-row wrapper
// element needed. Only a paragraph's last row gets the visual divider, so
// this still reads as flowing paragraphs, not a chopped-up table.
function renderDuplicateView() {
  els.galleysGrid.innerHTML = "";
  const charsPerLine = computeCharsPerLine();

  for (const paragraph of splitIntoParagraphs(currentTokens)) {
    const lines = splitParagraphIntoLines(paragraph, charsPerLine);
    lines.forEach((rowTokens, index) => {
      const isParagraphEnd = index === lines.length - 1;
      const originalCell = document.createElement("div");
      originalCell.className = "gcell gcell-original" + (isParagraphEnd ? " paragraph-end" : "");
      const gutterCell = document.createElement("div");
      gutterCell.className = "gcell gcell-gutter" + (isParagraphEnd ? " paragraph-end" : "");
      const setCell = document.createElement("div");
      setCell.className = "gcell gcell-set" + (isParagraphEnd ? " paragraph-end" : "");

      for (const token of rowTokens) {
        if (!token.is_word) {
          originalCell.appendChild(document.createTextNode(token.text));
          setCell.appendChild(document.createTextNode(token.text));
          continue;
        }
        const original = originalByPosition.get(token.position);
        originalCell.appendChild(document.createTextNode(original !== undefined ? original : token.text));
        const changed = correctionPositions.has(token.position) && original !== token.text;
        setCell.appendChild(wordSpan(token.text, token.position, changed ? "corr" : null));
      }

      els.galleysGrid.appendChild(originalCell);
      els.galleysGrid.appendChild(gutterCell);
      els.galleysGrid.appendChild(setCell);
    });
  }
}

// Places a small mark in each row's own gutter cell, at the vertical center
// of every changed word in that row's "Set" cell -- run only while the
// Duplicate view is actually visible, since a hidden element has no layout
// to measure.
function computeGutterMarks() {
  const cells = els.galleysGrid.children;
  for (let i = 0; i < cells.length; i += 3) {
    const gutterCell = cells[i + 1];
    const setCell = cells[i + 2];
    gutterCell.innerHTML = "";
    const gutterRect = gutterCell.getBoundingClientRect();
    for (const span of setCell.querySelectorAll(".corr")) {
      const rect = span.getBoundingClientRect();
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = "⌐";
      mark.style.top = (rect.top - gutterRect.top + rect.height / 2) + "px";
      gutterCell.appendChild(mark);
    }
  }
}

let gutterResizeTimer = null;
window.addEventListener("resize", () => {
  if (currentMode !== "duplicate" || els.pageResult.hidden) return;
  clearTimeout(gutterResizeTimer);
  // A width change can shift charsPerLine, so the rows themselves (not just
  // the marks) need rebuilding, or a row could now be wider/narrower than
  // what it was originally sized to fit.
  gutterResizeTimer = setTimeout(() => {
    renderDuplicateView();
    computeGutterMarks();
  }, 150);
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
  clearWordHighlight();
  if (mode === "duplicate") computeGutterMarks();
}

function activeViewContainer() {
  if (currentMode === "black") return els.viewBlack;
  if (currentMode === "blackred") return els.viewBlackRed;
  return els.galleysGrid;
}

function resultWordSpan(position) {
  return activeViewContainer().querySelector('.result-word[data-position="' + position + '"]');
}

// Both jumpToWord() (card -> text) and jumpToCard() (text -> card) leave a
// real box of inverted color in place for HIGHLIGHT_MS, then clear it --
// each tracks its own element/timer so highlighting one doesn't cut the
// other short.
const HIGHLIGHT_MS = 5000;
let highlightWordTimer = null;
let highlightCardTimer = null;

function clearWordHighlight() {
  clearTimeout(highlightWordTimer);
  if (highlightedWord) {
    highlightedWord.classList.remove("highlight");
    highlightedWord = null;
  }
}

function clearCardHighlight() {
  clearTimeout(highlightCardTimer);
  if (highlightedCard) {
    highlightedCard.classList.remove("highlight");
    highlightedCard = null;
  }
}

// Gives that word's span in the currently active view a real, persistent
// highlight (clearing any previous one) and scrolls it to the center of the
// page -- more visible and more reliable than a native text selection, which
// is easy to lose among 500 words and disappears the moment focus moves on.
function jumpToWord(position) {
  const span = resultWordSpan(position);
  if (!span) return;
  clearWordHighlight();
  span.classList.add("highlight");
  highlightedWord = span;
  span.scrollIntoView({ behavior: "smooth", block: "center" });
  highlightWordTimer = setTimeout(clearWordHighlight, HIGHLIGHT_MS);
}

// The reverse of jumpToWord(): clicking a replaced word in Blk+Red or
// Duplicate scrolls to its card in the corrections list and highlights that.
function jumpToCard(position) {
  const card = els.cardsRow.querySelector('.idx-card[data-position="' + position + '"]');
  if (!card) return;
  clearCardHighlight();
  card.classList.add("highlight");
  highlightedCard = card;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  highlightCardTimer = setTimeout(clearCardHighlight, HIGHLIGHT_MS);
}

// ============================= corrections cards =============================

function renderResult(data) {
  els.pageResult.hidden = false;
  els.correctionsPanel.hidden = false;
  currentTokens = data.tokens.map((t) => ({ ...t }));
  correctionPositions = new Set(data.replacements.map((r) => r.position));
  originalByPosition = new Map(data.replacements.map((r) => [r.position, r.original]));
  // A word whose text the server changed only as a side effect (currently
  // just an "a"/"an" fix -- see schemas.TextToken.original) isn't in
  // `replacements`, so it needs its true original recorded here too, or the
  // Duplicate view's "Original" galley would show the already-fixed text.
  for (const token of data.tokens) {
    if (token.is_word && token.original != null) {
      originalByPosition.set(token.position, token.original);
    }
  }
  clearWordHighlight();
  clearCardHighlight();
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
  card.title = "Find this word in the page";
  // The whole card jumps to its word in the page -- except its own
  // alt-chip/Reset controls, which do their own, more specific thing.
  card.addEventListener("click", (event) => {
    if (event.target.closest(".alt-chip, .reset-link")) return;
    jumpToWord(item.position);
  });

  const words = document.createElement("div");
  words.className = "words";
  const originalSpan = document.createElement("span");
  originalSpan.className = "word-original";
  originalSpan.textContent = item.original + " →";
  const wordLink = document.createElement("button");
  wordLink.type = "button";
  wordLink.className = "word-link";
  wordLink.textContent = item.replacement;
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
// Words cmudict would call a consonant sound despite a leading vowel letter
// ("university" starts like "y"), or a vowel sound despite a leading
// consonant letter ("hour" has a silent h) -- the same exceptions the
// server's pronunciation-based check (synreplace.inflect.starts_with_vowel_sound)
// catches for free. This client-side fallback (used only when Reset/an
// alternative swaps a word in without a server round-trip) has no
// pronunciation data to work from, so it hard-codes the common ones instead.
const VOWEL_SOUND_EXCEPTIONS = new Set([
  "university", "universal", "unique", "unicorn", "unicycle", "uniform",
  "union", "unit", "united", "unanimous", "usual", "user", "useful",
  "utility", "utopia", "european", "eucalyptus", "euro", "one", "once",
]);
const CONSONANT_LETTER_VOWEL_SOUND = new Set(["hour", "honest", "honor", "honour", "heir", "herb"]);

function wordStartsWithVowelSound(text) {
  const word = (text.split(/\s+/)[0] || "").toLowerCase();
  if (CONSONANT_LETTER_VOWEL_SOUND.has(word)) return true;
  if (VOWEL_SOUND_EXCEPTIONS.has(word)) return false;
  return /^[aeiou]/.test(word);
}

function fixArticle(article, followingText) {
  const correct = wordStartsWithVowelSound(followingText) ? "an" : "a";
  if (article === article.toUpperCase() && article.length > 1) return correct.toUpperCase();
  if (/[A-Z]/.test(article[0])) return correct[0].toUpperCase() + correct.slice(1);
  return correct;
}

function wordTokenAtPosition(position) {
  return currentTokens.find((t) => t.is_word && t.position === position);
}

function applyChoice(card, item, word, similarity, activeChip, allChips) {
  const token = wordTokenAtPosition(item.position);
  if (token) token.text = word;
  // Mirrors the same fix the server applies on the initial rewrite (see
  // synreplace.rewrite.rewrite_tokens) -- a Reset/alternative swap can just
  // as easily change whether the word now starts with a vowel sound.
  const articleToken = wordTokenAtPosition(item.position - 1);
  if (articleToken && ["a", "an"].includes(articleToken.text.toLowerCase())) {
    const fixed = fixArticle(articleToken.text, token ? token.text : word);
    if (fixed !== articleToken.text) {
      // Record its true original the first time it's ever touched (by the
      // server or a client-side edit, whichever happens first) so the
      // Duplicate view's "Original" galley stays correct even after this.
      if (!originalByPosition.has(articleToken.position)) {
        originalByPosition.set(articleToken.position, articleToken.text);
      }
      articleToken.text = fixed;
    }
  }
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

// ============================= help ============================= //

function openHelp() {
  els.helpOverlay.hidden = false;
  els.helpBtn.setAttribute("aria-expanded", "true");
  els.helpClose.focus();
  document.addEventListener("keydown", onHelpKeydown);
}
function closeHelp() {
  els.helpOverlay.hidden = true;
  els.helpBtn.setAttribute("aria-expanded", "false");
  document.removeEventListener("keydown", onHelpKeydown);
  els.helpBtn.focus();
}
function onHelpKeydown(event) {
  if (event.key === "Escape") closeHelp();
}
els.helpBtn.addEventListener("click", openHelp);
els.helpClose.addEventListener("click", closeHelp);
els.helpOverlay.addEventListener("click", (event) => {
  if (event.target === els.helpOverlay) closeHelp();
});

els.rewriteBtn.addEventListener("click", rewrite);
els.copyBtn.addEventListener("click", copyResult);
els.downloadBtn.addEventListener("click", downloadResult);
els.sampleBtn.addEventListener("click", pasteSampleText);
els.text.addEventListener("input", updateWordCount);
els.threshold.addEventListener("input", () => {
  els.thresholdValue.textContent = Number(els.threshold.value).toFixed(2);
});

updateWordCount();
