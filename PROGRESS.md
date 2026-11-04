# Progress Log

## Session 5, continued — Leakage judge (Phase 4, part 2 of ~3)

**Built, wired in, and verified for real - with one genuine, honestly-documented false positive.**

- `evals/leakage_judge.py`: `judge_diary_entry()`, a SEPARATE Claude call reviewing a completed
  diary entry for anachronisms. Deliberately the opposite instruction from Arthur's own
  generation: the judge is SUPPOSED to use its full historical knowledge - that's how it
  recognizes a violation.
- Wired into `fetch` (judges only newly-generated entries, not on every re-run) and `show`
  (displays a loud warning if flagged, so nothing is silently hidden even without a hard
  publish-block).
- **Real test with a deliberately leaky planted entry:** fed the real judge an entry mentioning
  the 1929 crash, Houdini's death stated as certain fact, television, and WWII starting in 1939.
  It correctly caught all 4, with accurate explanations - including correctly distinguishing
  Arthur's real, properly-hedged "physicians hold little hope" from this test's improperly
  definite "he will die this very week."
- **Real test against the actual existing diary entries** (Oct 29, 30, Nov 4 - generated before
  this feature existed) turned up a genuine **false positive**: the judge flagged Oct 29's
  Professor Hussey passage as suspicious, but that death was real 1926 news (verified earlier
  this session, straight from that day's actual Evening Star) - the judge's reasoning got
  confused by biographical detail that was likely in the real source article. **Root cause: the
  judge only sees Arthur's finished text, never the original source articles, so it can't verify
  "this detail came from the real newspaper" vs. "this sounds suspiciously specific."** Left the
  judgment as-is in the database (honest data, not hidden) rather than deleting an inconvenient
  result - documenting the limitation here instead.
- **Known limitation to revisit:** giving the judge the source articles alongside the diary
  entry (so it can check grounding, not just plausibility) would likely fix this false-positive
  class. Not built now - flagging for later, not silently working around it.
- 78 tests total, all green.

## Session 5 — 2026-11-04 (Phase 4, part 1 of ~3)

**Prediction Ledger complete and verified for real. Leakage judge, broader guardrails, and the
CI eval gate are still open - Phase 4 is NOT done yet, just its first piece.**

- Resolution method decided: fully automatic (your call) - Claude judges due predictions using
  ONLY our own accumulated real news (TodayHeadline/NewsSummary rows), never its own training
  knowledge, since these events may postdate its training cutoff.
- `Prediction`/`PredictionResolution` as two separate models/tables, both INSERT-only (not
  INSERT OR REPLACE) - saving the same id twice raises `sqlite3.IntegrityError` instead of
  silently overwriting. The honesty rule (immutable/append-only) enforced at the DB level.
- `outcome` is `"true"/"false"/"unclear"`, not a plain bool - "unclear" (not enough evidence) is
  an honest result, not a failure, and `brier_score()` correctly excludes it from scoring.
- Finance-topic guardrail (keyword filter, defense-in-depth beyond the prompt instruction) -
  same "don't trust prompting alone" lesson as leakage prevention. Didn't need to reject
  anything in the real run, but exists for when it does.
- Wired into `fetch` (generates + resolves, both idempotent), new `echoledger scorecard` CLI
  command, new `GET /scorecard` API endpoint.
- **Verified for real, twice:** (1) real `fetch` generated 3 genuine, non-financial, specific
  predictions from today's actual news (South Africa's ANC local elections, Japan's nuclear
  policy stance, a Ukraine-Russia ceasefire holding) - none were due for resolution yet.
  (2) To test resolution specifically (the riskier, more novel half), injected one synthetic
  test prediction with a known real answer ("will Erin Patterson's appeal succeed" - we already
  had the real answer stored from an earlier session: it was rejected) - Claude correctly
  resolved it "false," citing our own stored headline as evidence verbatim. Cleaned up the test
  prediction afterward so it doesn't pollute the real scorecard.
- 73 tests total, all green.

**What's left for Phase 4:**
- Automated leakage judge (deferred since Phase 2) - score Arthur's entries for anachronisms,
  not just trust the prompt instruction.
- Broader guardrails - prompt-injection defense for fetched text (we treat it as untrusted in
  principle, but have no actual check yet).
- Eval gate in CI - wire an evaluation check into GitHub Actions so a regression can fail a build.

## Session 4 — 2026-11-04 (Phase 3)

**Phase 3 complete: embeddings + Chroma vector search + History Echo, end-to-end.**

- Chose OpenAI `text-embedding-3-small` ($0.02/1M tokens) as the embeddings provider -
  `OPENAI_API_KEY` added to `.env`. Deliberately did NOT use LlamaIndex (named in the original
  roadmap) - hand-rolled the same functionality directly with OpenAI + Chroma, same reasoning as
  skipping LangChain earlier: thin, readable, no framework needed yet.
- `rag/embeddings.py`, `rag/vector_store.py` (Chroma, persists to `data/chroma/`), `rag/index.py`
  (idempotent embedding of HistoricalArticles/TodayHeadlines), `rag/echo.py` (time-filtered
  similarity search - a match can never be dated after Arthur's own historical date).
- **Verified Chroma's actual filter behavior empirically rather than assumed:** `$lte`/`$gte`
  require numeric values, not date strings (found via a real runtime error) - fixed with an
  integer `date_int` metadata field. The `$and` + bare-equality shorthand *does* work at runtime
  despite chromadb's type stubs being stricter than the real API (documented with targeted
  `type: ignore`, not blanket-suppressed).
- Hit the exact same field-shadowing mypy bug a third time (`EchoCandidate.date` before
  `historical_date`) - now documented in two places in the code.
- **Learned the Phase 2 lesson and applied it proactively this time:** built the RAG functions,
  then immediately asked "should I wire this into fetch/show/API now" instead of waiting to be
  caught. Wired `find_echo_candidates` to persist results (`echo_candidates` table) rather than
  recompute on every read - the same "cache everything, compute once" pattern as the diary entry.
- Verified for real against the full archive + live headlines: genuine thematic echoes found by
  embedding similarity alone, including a strong real midterm-election match - "Florida
  Republicans fend off Democrats... first black governor" (2026) matched to "DEMOCRATIC GAINS
  SEEN IN CONGRESS... G.O.P. Is Bankrupt Mentally and Morally" (1926) - landing on genuine
  Election Day 2026 news. Total embedding cost so far: under $0.01.
- 52 tests total, all green.

**Known gaps, stated plainly:**
- A few echo matches show "(no headline)" - some 1926 articles have no legible headline from the
  Phase 1 parser, but the body text still matched correctly. Cosmetic, not a correctness bug.
- No hybrid retrieval (keyword + semantic combined) - pure embedding similarity only.
- Running `fetch --date X` on a real calendar day other than X mislabels *current* RSS headlines
  under the wrong logical date, since RSS has no way to fetch "yesterday's top stories" - only
  "what's current right now." Not a bug, just means `fetch` should only ever be run with
  `--date today` in real daily use, never backfilled for the "today" side.

## Session 3 — 2026-10-30 (Phase 2)

**Phase 2 complete: Arthur writes, news gets summarized, both served over HTTP.**

- Chose Claude Haiku 4.5 as the LLM (cost-control fit for a no-budget project). API key set up
  in `.env` after a real security incident mid-setup: the first key got pasted into chat and had
  to be revoked/rotated before use - logged here as a reminder, never put secrets in chat.
- `llm/client.py` - thin Anthropic wrapper + **cost logging**: every call's tokens/cost go into a
  new `llm_usage` SQLite table (the non-negotiable "log tokens + cost per run" rule, actually
  implemented, not just documented).
- `llm/arthur.py` - `write_diary_entry()`, grounded in real HistoricalArticles, leakage prevention
  via prompting only (an automated leakage *judge* is Phase 4, not this). **Verified for real**
  against live Claude using real 1926-10-29 Evening Star articles - manual read found no
  detectable leakage (left the Senate corruption probe genuinely unresolved, no anachronisms).
  Real cost: $0.0039/entry.
- `llm/news_summary.py` - `summarize_headlines()`, batches a whole day's headlines into **one**
  API call (not one per headline) to save tokens, per explicit instruction. Verified for real
  against today's live BBC/Guardian/NPR headlines - genuine paraphrases, not copied snippet text.
  Real cost: $0.0040 for all 9 headlines in one call.
- `api/` - FastAPI app, `GET /today` and `GET /archive/{date}`. DB connection is a FastAPI
  dependency (`Depends(get_db)`) so tests override it instead of touching the real database file.
  Falls back to a headline's raw snippet when no summary exists yet, rather than showing nothing.
  Verified for real by running the actual server and hitting both endpoints.
- Real bug caught by mypy: a Pydantic field named `date` shadows the `date` *type* for every
  later field in that same class body - fixed by reordering fields.
- **Found and fixed a real gap right after declaring Phase 2 done:** `echoledger fetch` never
  actually called `write_diary_entry()`/`summarize_headlines()` - everything verified so far came
  from one-off manual scripts, not the real CLI. Fixed: `fetch` now generates both (idempotent -
  skips if already done, so re-running never double-spends), `show` now uses `build_daily_view()`
  (same function the API uses) instead of a stale pre-Phase-2 raw listing. Caught by the user
  asking "let's check how the output is actually coming."
- Re-verified end-to-end after the fix: correctly skipped 8 already-summarized headlines, paid
  for only 1 new one. Arthur's 1926-10-30 entry correctly reported Houdini as "gravely ill"
  without revealing his actual death the next day (Oct 31, 1926) - an unplanned, real test of
  leakage prevention against a famous historical event.
- 45 tests total, all green, none touching the network/LLM/real files.

**Phase 2 "done" per the original roadmap** (Arthur diary + summaries with structured output;
FastAPI read endpoints) - all three pieces built, tested, and verified against real data/APIs.

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
