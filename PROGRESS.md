# Progress Log

## Session 2 — 2026-10-30

**Milestone: `echoledger fetch` and `echoledger show` work end-to-end with real data.**

- Chose "Evening Star" (Washington D.C.) as Arthur's newspaper (`NEWSPAPER_KEY` in config.py).
- Chose RSS feeds for today's news: BBC News, The Guardian, NPR (all verified live).
- Built, tested, and committed: `models.py` (HistoricalArticle / TodayHeadline - two separate
  types so the copyright rule is structurally enforced, not just a convention),
  `storage/db.py` (SQLite, stdlib only), `utils/dates.py` (today()/years_ago(), handles Feb 29),
  `sources/american_stories.py` (parses scan-level JSON into articles, `ingest_year()` does the
  one-time full-year scan), `sources/rss.py` (fetches + hard-truncates snippets to 300 chars),
  `cli.py` (the `fetch`/`show` commands). 27 tests, all passing, no network/big-file dependency
  in the test suite itself (synthetic fixtures + httpx.MockTransport).
- **Real bug found and fixed while testing for real** (not caught by unit tests, since those use
  tiny fixtures): `save_historical_article` committed to SQLite after every row. A full year's
  ~65k articles meant 65k individual disk-sync commits — still running after 5+ minutes, killed
  it. Fixed to commit once at the end instead (also makes the whole year-ingest atomic). Real
  run after the fix: ~35 seconds for the full first-time ingest of 1926.
- Verified real output end-to-end: Evening Star's actual front page for 1926-10-29 (Coolidge
  visiting James Monroe's old home, a bandit sentencing, a Senate slush-fund probe) shown
  alongside live BBC/Guardian/NPR headlines for 2026-10-29.

- Added `.github/workflows/ci.yml` (checkout, Python 3.11, install, ruff, mypy, pytest).
- Created GitHub repo at https://github.com/shaiksaidagenai-oss/echoledger, pushed all commits.
  Hit a real snag: Windows had a stale cached GitHub login for a different account
  (`isk22083-eng`, unrelated to this project) which caused a 403 on push. Fixed by clearing
  that one cached credential via `cmdkey /delete:...` (the office GitLab credentials were left
  untouched - different host, unaffected). **CI ran green on the very first push.**

**Phase 1 "done" checklist status:**
- [x] `echoledger fetch`/`show` work with real data
- [x] pytest passes
- [x] GitHub Actions is green
- [ ] `docker run` executes the CLI - **last remaining item**

**Dockerfile written, but build is blocked — paused, not abandoned:**
- `Dockerfile` and `.dockerignore` are written and committed. `docker build` itself progresses
  fine (base image pulls, files copy) but hangs indefinitely at `pip install` - diagnosed as a
  **container networking problem, not a Dockerfile problem**: even a raw socket connection to a
  literal IP (bypassing DNS entirely) hangs from inside any container on this machine, while the
  Docker Desktop host app pulls images fine. Found two VPN-related services actively running
  (`FortiSSLVPNdaemon`, `openvpnserv`/`openvpnserv2`/`openvpn-gui`) even though their adapters
  show "Disconnected" - these commonly install low-level network filter drivers that interfere
  with Docker's internal virtual network regardless of connection state. Likely a work-machine/
  corporate-network issue, not something to fix mid-session.
- **Next step when revisited:** try restarting Docker Desktop fully first (simplest); if that
  doesn't help, check with IT or try on a non-office network. The Dockerfile itself should be
  correct as-is - this is purely an environment blocker on this one machine.

**Decision: Docker excluded from Phase 1's "done" bar for now.** The Dockerfile stays in the
repo as-is (believed correct) but its verification is deferred indefinitely until the network
blocker is resolved (different network, or IT help) - not required to consider Phase 1 complete.

## Phase 1 — Done (with the Docker exception above)

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
