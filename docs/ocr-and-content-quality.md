# OCR and content quality

How the ingestion lane recovers text from PDFs that have none, how it decides
whether that text is worth keeping, and why the quality gate was rejecting real
textbooks while accepting noise.

This document exists because two uploads failed in opposite directions on the
same day, and the fixes only make sense together.

---

## The two failures

### 1. A scanned PDF produced flashcards about the scanner

Uploading `Mechanisms of heat transfer.pdf` — two phone-camera images of a
handwritten notebook page — ingested **successfully** and generated flashcards
titled *CamScanner*, *PAGE*, *DATE*, *Kwad Res*.

The stored document was 330 characters:

```
0,08 \ A sDiyafecn ? 2,2xl0- 2 0, dtd ( ra) jo! iia igi a a yal - Te} Ta -Te)
Kwad Res r ? | \J-Te - [+h : ets 0/3799, TS Scanned with CamScanner PAGE DATE
Na. itomyiebieieeniigainaleahageaminiileibinasieaion isteameasices ge ...
```

Of the 20 alphabetic tokens longer than two characters, the only real words were
`scanned`, `with`, `camscanner`, `page`, `date`, `kwad`, `res` — every one of
them scanner watermark or notebook template. **Zero educational content was
recovered.** The topic extractor then did exactly what it was designed to do:
those words repeat on every page, so they ranked highest, so they became the
topics.

### 2. A real textbook was rejected

`university-physics-with-modern-physics-13th-edition.pdf` — 1,598 pages with a
proper text layer — failed with *"Document appears to contain highly repetitive
content."*

---

## Why the quality gate was inverted

`QualityChecker._check_repetition` divided distinct words by total words across
the **whole document**. That ratio falls as a document grows however varied its
prose: function words recur without limit while the stock of new words runs out
(Heaps' law). Length therefore read as repetition.

Measured:

| Document | unique-word ratio | Gate needs ≥ 0.20 | Verdict | Should be |
|---|---|---|---|---|
| 330 chars of OCR noise | **0.730** | ✅ | accepted | rejected |
| 1,598-page physics textbook | **0.019** | ❌ | rejected | accepted |

Noise scores *high* on that metric precisely because noise never repeats. The
gate was backwards in both directions at once.

**The fix.** Vocabulary richness is now measured per fixed window of
`REPETITION_WINDOW_WORDS = 2000` and averaged. Genuinely repetitive text scores
low in every window; a long varied document scores normally in each one. The
textbook moves from 0.019 to 0.381 and passes.

A short trailing window is folded back into its predecessor. Three words are
almost always three distinct words, so a 2,001-word document of pure repetition
would otherwise average `0.0005` and `1.0` into a comfortable pass.

### 3. …and then the transcription failed a *third* heuristic

With the handwritten notes finally transcribed, ingestion still refused them:
*"Document contains too little readable text."*

`_check_letter_ratio` counted **letters** against every character. It exists to
catch mojibake and binary junk, but a worked physics solution is legitimately 22%
digits and 23% operators, so it scored `0.292` against a `0.40` floor. The check
had quietly become a test for prose.

Counting **alphanumerics against non-whitespace** asks the intended question —
digits are content, whitespace is neither content nor noise:

| Content | letters / all chars | alnum / non-space |
|---|---|---|
| Worked physics transcription | 0.243 ❌ | **0.680** ✅ |
| Ordinary prose | 0.850 | 0.979 |
| Physics textbook | 0.723 | 0.941 |
| Box-drawing mojibake | 0.000 | 0.000 ❌ |
| Control-character junk | 0.000 | 0.000 ❌ |

All three failures share one shape: **a heuristic measuring something adjacent to
the question it was asked.** Worth remembering the next time one is added.

---

## Why filtering could not fix the scanned PDF

The instinct is to strip the junk and keep the rest. There is no rest.

**Stripping the furniture leaves nothing.** `strip_scanner_furniture()` removes
the watermark and template fields. Lexicality — the share of tokens that are
recognisable words — goes from `0.095` with them to **`0.000`** without. The
watermark *was* the only English on the page.

**Filtering by confidence makes it worse.** Tesseract reports per-word
confidence. Keeping only `conf >= 70` on this page keeps:

```
['0,08', '(', 'Ta', 'Res', '-', 'TS', 'Scanned', 'with', 'CamScanner']
```

The most confident text on a handwritten page is the *printed* watermark. A
confidence filter keeps exactly the junk you wanted removed.

**No Tesseract setting helps.** Verified across 8 configurations — DPI 300 and
500 × PSM 3, 4, 6, 11. Every word Tesseract got right was printed; every word it
got wrong was handwritten. That is not a tuning problem: Tesseract is trained on
printed text and does not do handwriting recognition.

---

## The pipeline now

```
PDF ──► TextParser
         │
         ├─ has a text layer ──────────────────────────────► QualityChecker ─► store
         │
         └─ no text layer
              │
              ▼
          ENABLE_OCR?  ── no ──► refuse: "scanned or image-only, OCR is switched off"
              │ yes
              ▼
          Tesseract (ocr_pdf) ──► strip_scanner_furniture()
              │
              ▼
          ocr_looks_readable()?   lexicality ≥ 0.08  AND  mean confidence ≥ 55
              │                        │
              │ yes                    │ no
              ▼                        ▼
       source_type="file-ocr"    ENABLE_VISION_OCR? ── no ──► refuse, naming the
              │                        │ yes                  actual diagnosis
              │                        ▼
              │                  vision model transcribes the pages
              │                        │
              │                        ▼
              │                 source_type="file-vision-ocr"
              ▼                        ▼
                      QualityChecker ─► store
```

The key change is that OCR output is now **judged before it is accepted**.
Previously anything non-empty was passed straight to the quality gate, which had
no way to tell recognised text from recognised noise.

---

## Modules

| File | Responsibility |
|---|---|
| `src/ingestion/ocr.py` | Tesseract; furniture stripping; *did OCR work?* |
| `src/ingestion/vision_ocr.py` | Vision-model transcription via the LiteLLM gateway |
| `src/ingestion/quality.py` | *Is this a usable document?* (windowed repetition) |
| `src/ingestion/loader.py` | The escalation, and recording provenance |

### Why lexicality lives in `ocr.py`, not `quality.py`

It is applied **only** to OCR output, never to ordinary uploads. The margin is
too narrow to gamble a user's document on:

| Text | Lexicality |
|---|---|
| OCR noise, furniture stripped | **0.000** |
| `demo_data.py` — "A database is an organized collection…" | 0.143 |
| `test_ingestion_batch.py` fixture | 0.167 |
| Vision transcription of the same page | 0.647 |
| Physics textbook | 0.418 |

A universal threshold would sit in a 0.14-wide gap with an arbitrary word list
behind it, and technical, non-English or heavily notated prose could legitimately
score low. Restricting it to OCR output — where the failure mode is known and the
alternative is storing garbage — keeps the risk where it belongs.

So: `ocr.py` owns *"did OCR work?"*, `quality.py` owns *"is this a usable
document?"*.

---

## Configuration

All keys are documented in `.env.example`. Everything is off by default.

| Key | Default | Purpose |
|---|---|---|
| `ENABLE_OCR` | `false` | Run Tesseract on PDFs with no text layer |
| `TESSERACT_CMD` | — | Only if the binary is off PATH and outside the standard locations |
| `ENABLE_VISION_OCR` | `false` | Escalate unreadable pages to a vision model |
| `VISION_OCR_MODEL` | `qwen/qwen3-vl-8b-instruct` | Which model transcribes |
| `VISION_OCR_MAX_TOKENS` | `1500` | Per-page output cap |

### Installing Tesseract

It is a **system binary**, not a Python package. `pip install pytesseract` alone
does nothing.

- Windows: [UB-Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki), or `choco install tesseract`
- macOS: `brew install tesseract`
- Debian/Ubuntu: `apt-get install tesseract-ocr`

Both Windows installers write to `C:\Program Files\Tesseract-OCR` and update only
the **user** PATH, so any already-running process reports "binary not found" with
the executable sitting right there. `find_tesseract()` therefore checks
`TESSERACT_CMD`, then PATH, then the standard install locations.

Note also that the ingestion lane calls `load_dotenv()` itself. It is importable
on its own — `streamlit run src/ingestion/ui.py` loads none of the agent modules
that happen to call it elsewhere — so without that, `ENABLE_OCR` would be honoured
by the combined app and silently ignored by the standalone upload page.

---

## The provenance problem

**A vision transcription is model output, not extracted text**, and that matters
more here than it would in most projects.

Everywhere else in this codebase a citation points at text a human supplied; a
chunk is evidence. A transcribed page is a *reconstruction*. A hallucinated line
would be indistinguishable from a real one and would then be cited as though it
were source material — inside a system whose entire premise is grounding and
provenance.

Mitigations in place:

- Vision transcription is **opt-in** and only ever escalates for pages Tesseract
  failed to read. A printed scan it read correctly never reaches the model.
- The prompt instructs transcription only — *"do not explain, summarise, correct
  or complete the work"* — and marks unreadable regions `[illegible]` rather than
  guessing.
- `temperature=0`.
- Documents carry `source_type="file-vision-ocr"`, so a reviewer can tell which
  kind of source they are citing.

**This is not sufficient on its own.** Documents recovered this way should be
treated as pending human verification, not as ground truth. That judgement is
deliberately left to the review lane rather than being hidden inside ingestion.

---

## Cost and limits

The gateway is credit-limited. An uncapped first attempt returned:

```
402: This request requires more credits, or fewer max_tokens.
     You requested up to 65536 tokens, but can only afford 3333.
```

It refuses on the **requested ceiling**, not on what the answer would actually
use, so `max_tokens` is always sent explicitly. Pages are rendered at 120 DPI to
keep the inline image small while staying legible.

The default model is small on purpose: on the page this was built for,
`qwen/qwen3-vl-8b-instruct` transcribed *more* of the working than
`google/gemini-3.5-flash`.

---

## Testing

`tests/features/test_ingestion_ocr.py`. Two rules:

1. **No test touches the gateway.** `_FakeVisionClient` is injected via the
   `client` parameter of `transcribe_pdf()`.
2. **The fixtures are real.** `REAL_OCR_NOISE` is the exact 330 characters
   Tesseract produced; `REAL_VISION_TRANSCRIPTION` is what a vision model
   returned for the same page. An invented noise string would be too easy to
   catch and would prove nothing.

Every test in this area was mutation-tested — the defect was reintroduced and the
test confirmed to fail — covering: accepting unreadable OCR, skipping the
furniture strip, and escalating when Tesseract had in fact succeeded.

The one test that needs real Tesseract skips when the binary is absent, so CI
proves the behaviour without requiring a system install.

---

## Known limits

- **Only the top-level `references` shape of scanner furniture is handled.** The
  patterns cover CamScanner and one notebook brand. Another scanner app's
  watermark will not be stripped until its pattern is added.
- **English only.** `lexicality()` scores against a small English word list, so a
  genuine Arabic or French scan would read as noise and escalate to vision. That
  is the safe direction to fail, but it means vision gets used more than it needs
  to for non-English documents.
- **The textbook produces 7,470 chunks** at `chunk_size=1000, overlap=100`.
  Ingestion itself is fine — measured at **11.3 s** for 6.7M characters, leaving
  a 17.5 MB database — but retrieval over a corpus containing it will be
  dominated by that one document. No cap has been added; the number to watch is
  retrieval quality, not ingestion time.

## Measured end to end

Both real documents, through the real pipeline:

| | Before | After |
|---|---|---|
| Handwritten notes | 330 chars of noise, `source_type=file` | 650 chars of physics, `source_type=file-vision-ocr` |
| Extracted topics | CamScanner, PAGE, DATE, Kwad Res | Mechanism, heat, transfer, Assignment |
| 1,598-page textbook | rejected as "highly repetitive" | 7,470 chunks in 11.3 s |
