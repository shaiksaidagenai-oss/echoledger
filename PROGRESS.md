# Progress Log

## Session 1 — 2026-10-29

**Done:**
- Discussed and locked product idea (see CLAUDE.md vision).
- Explored India-based 1926 source (Amrita Bazar Patrika) — rejected due to AWS WAF blocking
  automated access + unverified OCR quality.
- Explored Chronicling America / loc.gov directly — rejected: Cloudflare bot-blocked since
  2026-10-26 (confirmed independently, not specific to us). Checked 5 other NDNP partner sites
  (CA, VA, CO, UT, NY) — all similarly blocked.
- Found and verified the **American Stories** dataset on Hugging Face as the real 1926 data
  source — reachable, free, CC-BY-4.0, already-OCR'd, structured per-article JSON.
- Created Python venv (`EchoLedger/`, Python 3.13.1).
- Scaffolded the repo: `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `CLAUDE.md`,
  base `src/echoledger/` package + `tests/` folders. `git init` done, not yet committed.
- Started downloading `faro_1926.tar.gz` (~1.1 GB) into `data/raw/` (background task, completed).

**Verified (2026-10-29, same session):**
- `faro_1926.tar.gz` fully downloaded (1,225,152,593 bytes, matches expected size) into
  `data/raw/` (gitignored). Contains 85,107 article/scan JSON files for all of 1926.
- Oct 29, 1926 confirmed present with real, legible content across multiple newspapers, incl.
  "Evening Star" (Washington D.C., strong volume, 71 legible regions on page 1 alone — recommend
  as Arthur's primary title), "The Washington times." (covers the real Aimee Semple McPherson
  scandal cleanly), "New Britain herald." (CT, smaller). OCR quality verdict: genuinely usable,
  readable English with scattered period-typical noise; each region pre-tagged
  `"legibility": "Legible"/"Questionable"` so low-quality text can be auto-filtered.
- Note: the raw per-file JSON is **scan-level** (one whole page, many article bounding boxes with
  `raw_text`/`class`/`legibility` each), not pre-split article-level records — our ingestion code
  needs to do that splitting/filtering ourselves (the `datasets` library would do it for us, but
  we're avoiding that dependency per the plan to use plain httpx + manual parsing).

**Open / next step:**
- Shortlist 1–3 RSS feed URLs for "today's news".
- Install dev dependencies (`pip install -e ".[dev]"`) and confirm `pytest`/`ruff`/`mypy` run.
- First commit.
- Then: date-math module (today → 100 years ago, Asia/Kolkata, Feb 29 handling) with tests.

**Known limitations / risks to revisit:**
- 1926 article-selection strategy is currently "just pick 1-3 notable articles" — smart matching
  to today's top story is a later (Phase 3+, embeddings) feature, not Phase 1.
- Haven't yet verified real OCR quality from American Stories dataset firsthand (only verified
  the file exists, is reachable, and its documented structure).
