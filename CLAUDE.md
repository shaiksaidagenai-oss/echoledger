# EchoLedger — Project Context for Claude

## Vision

EchoLedger (public brand: "Then & Now") is a daily AI-generated, human-approved publication
with four sections:
1. **100 Years Ago Today** — "Arthur", a fictional 1926 citizen, writes a diary entry based on
   that day's real 1926 newspaper. He must never reveal knowledge of events after his current date.
2. **Today's Top 10** — today's most important world news, summarized in our own words, linking
   to original sources.
3. **Prediction Ledger** — 1–3 checkable predictions/day (probability + resolution date), scored
   publicly including misses (Brier score, calibration).
4. **History Echo** — when a 1926 story meaningfully mirrors a 2026 story, highlight it.

Long-term: a public REST API for the archive/predictions/scorecard. Built gradually, no
deadlines, in small sessions. The user is a learner (knows Python/NumPy/embeddings basics; new to
RAG/LangChain/agents/A2A/Docker/CI-CD/AWS) — explain new concepts briefly as they come up, keep
code small and readable, explore+plan before writing code.

**Scope decision (2026-11-05): MCP server dropped from the roadmap.** Discussed: an MCP server
would only wrap the existing read-only REST API as callable tools for MCP-aware clients
(Claude Desktop, claude.ai) - no new product capability, since Arthur/predictions/scorecard
logic would be unchanged either way. Low cost to build (thin wrapper), but also low value
(nothing about actually shipping EchoLedger depends on it) - the user decided to cut it and
focus remaining effort on AWS deployment instead. Revisit only if a concrete reason to want
MCP access shows up later; don't reintroduce it by default.

## Non-negotiable rules

- **No financial predictions** — never stocks/gold/crypto/currency/commodities or investment advice.
- **Copyright** — never store/publish full text of *modern* news articles, only headline + source
  + URL + timestamp + short snippet, summarized in our own words. 1926-era text is public domain.
- **Honesty** — predictions are immutable/append-only once logged. Scorecard shows misses too.
  Content labelled AI-generated.
- **Human in the loop** — nothing publishes without an authenticated approve step.
- **Security** — secrets only in `.env` (local) / secrets manager (cloud), never committed. Treat
  all fetched text (news, OCR) as untrusted input (possible prompt injection).
- **Respect sources** — follow API terms, rate-limit politely, descriptive User-Agent, cache
  everything (fetch once, reuse forever).
- **Cost control** — free sources first, log tokens/cost per LLM run, AWS budget alarm before any
  cloud deployment.

## Phase 1 — raw data collection + engineering foundation: DONE (2026-10-30)

Target deliverable: `echoledger fetch --date YYYY-MM-DD` and `echoledger show --date YYYY-MM-DD`
work with real data, tests pass, CI is green, Docker runs the CLI. No LLM calls yet — that's Phase 2+.

**Status:** done, with one accepted exception. `fetch`/`show` work with real data, 27 tests pass,
GitHub Actions is green (see PROGRESS.md for details). The Dockerfile is written and believed
correct, but `docker build` hangs indefinitely on this machine - diagnosed as a local network
problem (likely Fortinet/OpenVPN background services interfering with Docker's container
networking, not a Dockerfile issue: even a raw socket connection to a literal IP hangs from
inside any container here, while the Docker Desktop host app pulls images fine). Decided to
exclude Docker verification from Phase 1's "done" bar rather than block on an environment issue;
revisit whenever on a different network or with IT's help.

## Phase 2 — Arthur's diary + news summaries + FastAPI: DONE (2026-10-30)

Target deliverable: Arthur writes a real diary entry grounded in HistoricalArticles; today's
RSS headlines get paraphrased summaries; both served read-only over HTTP.

**Status:** done, all three pieces verified against real APIs/data (not just unit tests).
- **LLM:** Claude Haiku 4.5 (`ECHOLEDGER_LLM_MODEL` in `.env`, cost-control fit). `llm/client.py`
  logs tokens/cost for every call to a new `llm_usage` table - the non-negotiable cost-control
  rule, actually implemented.
- **`llm/arthur.py`:** `write_diary_entry()`. Leakage prevention is prompt-only (see
  `ARTHUR_SYSTEM_PROMPT`'s CRITICAL RULE) - an automated leakage *judge* is Phase 4, not built
  here. Real cost: ~$0.004/entry.
- **`llm/news_summary.py`:** `summarize_headlines()`, batches one whole day's headlines into a
  single API call (not one per headline) to save tokens. Real cost: ~$0.004 for 9 headlines.
- **`api/`:** FastAPI, `GET /today` + `GET /archive/{date}`, DB connection via
  `Depends(get_db)` so tests never touch the real database file.
- 45 tests, all passing without network/LLM/real-file access.

**Security incident during setup (resolved, logged for the record):** a real Anthropic API key
was pasted into chat by mistake. Treated as compromised immediately, revoked, and rotated before
any use - **never paste a secret into the conversation; put it directly in `.env` instead.**

## Phase 3 — embeddings + vector search + History Echo: DONE (2026-11-04)

Target deliverable: 1926 articles + today's headlines embedded into a vector store;
time-filtered similarity search; History Echo matches found and surfaced via `show`/the API.

**Status:** done, verified against the full real archive + live headlines, not just unit tests.
- **Embeddings:** OpenAI `text-embedding-3-small` (`OPENAI_API_KEY` in `.env`, $0.02/1M tokens).
  Did NOT use LlamaIndex despite it being named in the original roadmap - hand-rolled with OpenAI
  + Chroma directly, same reasoning as skipping LangChain: no framework needed yet.
- **`rag/vector_store.py`:** Chroma, persists to `data/chroma/` (gitignored).
- **`rag/index.py`:** idempotent embedding of HistoricalArticles/TodayHeadlines - skips anything
  already indexed by ID, never re-pays OpenAI for the same text twice.
- **`rag/echo.py`:** `find_echo_candidates()` - time-filtered (`date_int <= max_historical_date`)
  so a match can never be dated after Arthur's own historical date. Results persisted
  (`echo_candidates` table), not recomputed on every read.
- **Empirically verified, not assumed:** Chroma's `$lte`/`$gte` require numeric values, not date
  strings (found via a real runtime error - fixed with an integer `date_int` field).
- Real result worth remembering: "Florida Republicans fend off Democrats... first black
  governor" (2026) matched by pure embedding similarity to "DEMOCRATIC GAINS SEEN IN CONGRESS...
  G.O.P. Is Bankrupt Mentally and Morally" (1926) - a genuine midterm-election echo across
  exactly 100 years.
- 52 tests, all passing without touching the real vector store or making real API calls.

## Phase 4 — predictions, leakage judge, guardrails, eval gate: DONE (2026-11-04)

Target deliverable: checkable predictions scored over time; an automated check on Arthur's
leakage (not just the prompt instruction); basic guardrails; a real-API eval gate in CI.

**Status:** done, all four pieces verified for real, not just unit tests.
- **Prediction Ledger:** `Prediction`/`PredictionResolution` as two separate, INSERT-only
  tables (saving the same id twice raises `IntegrityError` - immutability enforced at the DB
  level). Resolution is fully automatic (user's call) but grounded ONLY in our own accumulated
  real news, never Claude's training knowledge. `outcome` is "true"/"false"/"unclear" -
  "unclear" is an honest result, correctly excluded from `evals/brier.py`'s Brier score.
- **Leakage judge** (`evals/leakage_judge.py`): a separate Claude call reviewing a completed
  diary entry - the judge is SUPPOSED to use full historical knowledge (opposite of Arthur's own
  generation). Verified for real: caught all 4 violations in a deliberately leaky planted entry
  (1929 crash, Houdini's death stated as fact, TV, WWII). **Also found a genuine false positive**
  on Arthur's real Oct 29 entry (flagged real, legitimate 1926 news as suspicious) - root cause:
  the judge never sees the original source articles, so it can't verify grounding. Left in the
  database and documented rather than hidden - a real limitation to revisit.
- **Guardrails:** finance-topic keyword filter (predictions), prompt-injection detection +
  `<tag>`-delimited untrusted content in every prompt (verified for real: a planted "IGNORE ALL
  PREVIOUS INSTRUCTIONS" injection was completely ignored by the real model), copyright
  similarity check (a summary that echoes its source gets rejected, falls back to the raw
  snippet). API auth/rate limiting deliberately NOT built - no public exposure yet, revisit at
  Phase 6.
- **Eval gate in CI:** `tests/test_real_leakage_eval.py`, a golden-set eval against the REAL
  API, marked `real_api` and excluded from the default (free, fast) `pytest` run. New
  `.github/workflows/eval.yml` runs it weekly + on manual dispatch. `ANTHROPIC_API_KEY` GitHub
  secret added and confirmed working via a real manual-trigger run.
- 87 tests total (85 fast + 2 real-API), all passing.

## Phase 5 — LangGraph + human approval + A2A Verification agent: DONE (2026-11-05)

Target deliverable: the daily workflow uses real multi-step orchestration (LangGraph) with a
genuine human-approval pause; a separate Verification agent reached over A2A.

**Status: done, both halves verified for real.** Deliberately split into two sessions -
LangGraph + A2A + a new data-model change all at once would be too much new surface area at once.

- **Part 1:** `agents/diary_workflow.py` - Arthur's write -> judge -> approve -> finalize sequence
  as a real LangGraph `StateGraph`, using `interrupt()`/`Command(resume=...)` to genuinely pause
  for a human decision (not a simulation). Scoped to just the diary entry (user's call) -
  `ArthurDiaryEntry` gained `approved: bool`; `build_daily_view` hides unapproved text behind a
  `diary_pending` flag instead of showing it. A rejection isn't final either - a reviewer can ask
  for a fresh draft instead (up to `max_attempts`), looping `write -> judge -> approval` back on
  itself via `add_conditional_edges()`.
- **Part 2:** the leakage judge now runs as `services/verification_agent/`, a standalone FastAPI
  server exposing it as an A2A skill, called over the network via a new `judge_via_a2a` client
  (`agents/verification_client.py`) injected into `judge_node` the same DI way as every other
  external API in this project.
- **Real bugs caught only by actually running the code, not by unit tests or static checks**
  (full list with root causes in PROGRESS.md Session 6/7): a raw Pydantic object surviving in
  graph state despite LangGraph's checkpointer serializing everything; Windows PowerShell's
  `"y" | command` silently prepending a UTF-8 BOM to stdin; a missing `await` on an async
  `create_client()` the SDK's type stubs made easy to miss; A2A requiring a `Task` to be
  enqueued before any status update references it; a message sent with the wrong default
  `role`; and `EventQueue.enqueue_event()` being async in a way `inspect.signature()` didn't
  reveal, silently dropping the enqueued Task until `await`ed.
- **Verified for real end-to-end:** started the Verification agent as its own OS process, called
  it from a separate Python process over real HTTP/JSONRPC, and confirmed in the database that
  the *server* (not the caller) persisted its own `leakage_judgments` row - genuine
  independent-service behavior, not an in-process call dressed up to look like one.
- The installed `a2a-sdk` is protobuf-based (`a2a.types.*` are generated `MessageMeta` classes),
  not the Pydantic models some tutorials describe - confirmed via `.DESCRIPTOR.fields`
  introspection rather than trusting docs, which also named a module path
  (`a2a.server.request_context`) that doesn't exist in this version (real path:
  `a2a.server.agent_execution`).
- 92 tests total, all green. Ruff and mypy clean.

## Phase 6 — AWS deployment: DONE (2026-11-06)

Target deliverable: EchoLedger containerized and running in AWS, with a persistent data store,
secrets out of `.env`, a budget alarm, and an automated (GitHub Actions) deploy pipeline.

**Status: all sessions A-F done.** Broken into small sessions (A: account safety net,
B: secrets migration, C: build image in CI, D: persistent storage, E: compute + go live,
F: verify + wrap up).

### Live resource reference (so a future session doesn't have to rediscover these)

Account `529470780389`, region `ap-southeast-2`. Local AWS CLI profile: `echoledger`
(`aws login --profile echoledger` to refresh when expired).

- ECR repo: `echoledger` (`529470780389.dkr.ecr.ap-southeast-2.amazonaws.com/echoledger`)
- ECS cluster: `echoledger`; service: `echoledger` (task def family: `echoledger`)
- **Service is currently scaled to 0** (`desiredCount: 0`) to stop compute billing between
  sessions - scale back up with `ecs:UpdateService(desiredCount=1)` before trying to reach the
  live endpoint again; its public IP changes on every new task, re-fetch it via the task's ENI.
- EFS file system: `fs-0bdb392946541090a`; access point: `fsap-0b16f15a72cbb283e`
  (`/echoledger-data`, mounted at `/data` in the container)
- Secret: `echoledger/api-keys` (both API keys, one JSON secret)
- IAM roles: `echoledger-deploy` (broad, human/CLI use), `echoledger-github-actions` (OIDC,
  CI only), `echoledger-ecs-execution` (ECS agent), `echoledger-ecs-task` (running container -
  EFS + Secrets Manager only)
- Budget: `EchoLedger-Monthly`, $20/month, email alerts

### Session F — final verification + scale down

- Full local toolchain (ruff/mypy/pytest) still clean after all of this phase's changes.
- Checked every piece together in one pass rather than trusting each session's individual
  verification to still hold: budget `HEALTHY`, 6 images in ECR, ECS service `1/1 running`,
  EFS `available`, secret present - then hit the live API one more time for real (`/scorecard`
  → `200 OK`) before touching anything.
- **Scaled the service to 0** (`desiredCount: 0`, confirmed `runningCount` actually reached 0,
  not just that the API call succeeded) - stops Fargate compute billing between sessions. EFS
  storage, the ECR images, secrets, IAM roles, and the task definition all persist untouched, so
  resuming later is just `ecs:UpdateService(desiredCount=1)` away, not a rebuild.

### Session A - account safety net

This account (`529470780389`, "Hello World") is an AWS Organization member account managed
through **IAM Identity Center** - the login identity ("Shaik") federates into a role per
account, rather than a classic root email/password. Root genuinely has no password and no MFA
(`AccountPasswordPresent: 0`, `AccountMFAEnabled: 0` via `iam:GetAccountSummary`) - not a gap to
fix, just how this account type works; nothing can log in as root here, so it isn't a real
attack surface. Deliberately did NOT chase Identity-Center-level MFA either - that instance
lives in a separate organization-management account outside this project's scope.

The account-creation flow's "$20/month spend limit" does NOT show up in AWS's standard Budgets
API (confirmed via `budgets:DescribeBudgets` returning empty) - created a real, standard AWS
Budget instead (`EchoLedger-Monthly`, $20 USD/month, email alerts at 80%/100% actual +
forecasted-over-100%), confirmed `HealthStatus: HEALTHY`. This is what actually satisfies the
non-negotiable budget-alarm-before-deployment rule.

Installed the **Agent Toolkit for AWS** (official AWS MCP server) so Claude acts on AWS directly
via tool calls (`mcp__aws-mcp__aws___run_script`, using `call_boto3`) instead of narrating
console steps. Two real setup bugs: (1) its MCP server launches via `uvx`, needing the separate
`uv` package manager - missing on this machine, caused silent `CONNECTION_CLOSED` until
installed; (2) the generated MCP config was missing `AWS_MCP_PROXY_PROFILES`, so it silently
defaulted to this machine's pre-existing, unrelated `default` AWS profile (a different real
account, likely an office one) - caught only by checking `sts:GetCallerIdentity` before acting,
not by assuming the profile was right. Fixed by pinning `AWS_MCP_PROXY_PROFILES=echoledger` in
`.claude.json`'s `aws-mcp` entry. **Standing rule (saved to memory)**: always verify the exact
AWS account number before any AWS action in this project, every session.

Created IAM user `echoledger-deploy` with `PowerUserAccess` (broad access, user's explicit call,
to narrow later once exact permission needs are known).

### Session B - secrets migration

`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` now also live in AWS Secrets Manager (`echoledger/api-keys`,
one JSON secret for both). `config.py`'s `_load_secrets_from_aws()` only activates when
`ECHOLEDGER_SECRETS_ARN` is set (never true locally) - populates `os.environ` via `setdefault`
before the Anthropic/OpenAI SDKs read their keys, same DI pattern as every external API call in
this project. Verified for real against the actual secret (not just a mocked client). Real
local-only snag: the `echoledger` CLI profile's `aws login` credential type needs
`botocore[crt]`, which plain `boto3` doesn't pull in - doesn't affect the deployed container,
which uses an IAM role instead.

### Session C - build + push to ECR in CI

Finally verifies the Dockerfile for real (open exception since Phase 1 - local `docker build`
hangs on this machine's VPN setup; building in GitHub's clean network sidesteps it).
`.github/workflows/deploy.yml` builds and pushes to a new ECR repo (`echoledger`) on every push
to `master`, authenticating via **OIDC** (no stored AWS secret in GitHub - a role trusted only
for this repo's `master` branch). Real bug: GitHub's OIDC `sub` claim now appends immutable
numeric IDs after the owner/repo names (`repo:OWNER@id/REPO@id:ref:...`, not the plain format
most docs show) - a newer anti-rename-hijack protection, diagnosed via CloudTrail (shows AWS's
actual-received claim) rather than the uninformative generic `AccessDenied` in the Actions log.

### Session D - persistent storage

Real, verified finding that changed the Session E plan - App Runner (originally assumed compute
target) is explicitly stateless per AWS's own docs, no EFS support. Moved to **ECS Fargate**
instead, which supports EFS volumes natively. Created the EFS file system + an access point
scoped to `/echoledger-data` (POSIX uid/gid `0:0`, matching the Dockerfile's root user) + mount
targets in the default VPC's 3 subnets, all confirmed `available`. No app code changes needed -
`ECHOLEDGER_DATA_DIR` already drove `DATA_DIR`/`DB_PATH`/Chroma's path since Phase 1.

### Session E - compute + go live

EchoLedger is genuinely running in AWS. Dockerfile now defaults to serving the FastAPI API
(`uvicorn`), CLI still reachable via command override for a future scheduled ingest task (not
built - deliberately out of scope). ECS Fargate cluster/service (`echoledger`), two IAM roles
(execution role for the ECS agent; narrowly-scoped task role for the running container's Secrets
Manager + EFS access), EFS mounted at `/data`. No ALB/NAT gateway - the task gets a public IP
directly, good enough for a solo project at this stage. **Verified for real**: hit the live
public endpoint, got genuine `200 OK` responses, confirmed in CloudWatch logs.

Afterward, populated the live environment with real data: bridged the local, already
human-approved database (344MB) onto the live EFS volume via a temporary S3 bootstrap step and a
non-interactive one-off ECS task, rather than faking the human-approval step for a fresh live
fetch (the A2A Verification agent isn't deployed, and true interactive approval isn't achievable
through current tooling - flagged both rather than working around them). Verified byte-for-byte;
confirmed real, previously-approved content now serves correctly, with `diary_pending` still
correctly gating unapproved dates.

### Session F - final verification + scale down

Checked every piece together in one pass: budget `HEALTHY`, ECR images present, ECS service
`1/1 running`, EFS `available`, secret present, full local toolchain (ruff/mypy/pytest) still
clean - then hit the live API one more time for real before touching anything. **Scaled the
service to 0** (confirmed `runningCount` actually reached 0, not just that the API call
succeeded) to stop Fargate compute billing between sessions - EFS storage, ECR images, secrets,
IAM roles, and the task definition all persist untouched, so resuming is one
`ecs:UpdateService(desiredCount=1)` call away, not a rebuild.

### Key decision: 1926 data source

**Decided: US, "American Stories" dataset on Hugging Face**
(`huggingface.co/datasets/dell-research-harvard/AmericanStories`), NOT Chronicling America's live
API, and NOT an India-based source. Reasoning, for future reference:

- We first explored an **India edition** (Amrita Bazar Patrika, British Library EAP262). Rejected:
  the British Library site (`eap.bl.uk`) blocks repeated automated requests with an AWS WAF
  challenge after the first request, and OCR quality was never verifiable (no existing
  transcription, bilingual English/Bengali pages, originals recovered in "paper-pulp state").
- We then tried **Chronicling America** (the originally planned US source) directly via
  `loc.gov`. As of **26 Oct 2026**, `www.loc.gov` (including the old `chroniclingamerica.loc.gov`,
  which now redirects there, and the new bulk-datasets portal) returns `403` from a **Cloudflare
  bot challenge** on every scripted request — confirmed via an independent public bug report, not
  specific to our setup. No JS-executing script can pass this without browser automation.
  Five other NDNP state-partner sites (CA, VA, CO, UT, NY) were tested and are **all** similarly
  bot-walled — this is industry-wide on historic-newspaper sites, not a single-source problem.
- **Resolution:** the "American Stories" dataset (Dell, Carlson, et al., Harvard/MIT/Princeton/NYU,
  arXiv:2308.12477) mirrors Chronicling America's scans but is hosted on Hugging Face, fully
  reachable with no bot wall, no login, CC-BY-4.0 licensed. One file per year
  (`faro_<year>.tar.gz`, ~1.1 GB for 1926), each containing per-article JSON:
  `{article_id, newspaper_name, edition, date, page, headline, byline, article}`.
- **Fetch model:** download a year's `.tar.gz` **once per real-world year** (not daily — "100
  years ago" stays in the same historical year for all of a given calendar year), extract/filter
  to our chosen newspaper title(s) + the specific dates actually needed, store only that in
  SQLite. Never bulk-load a whole year's data into the app's working set at once.
- Must cite: Dell et al., "American Stories: A Large-Scale Structured Text Dataset of Historical
  U.S. Newspapers," arXiv:2308.12477 (CC-BY-4.0).

### Open items (not yet decided)

- Newspaper (Evening Star) and RSS feeds (BBC/Guardian/NPR) are resolved — see above.
- Arthur's own diary still picks "first 6 front-page articles," not a RAG-retrieved relevant
  set - the embeddings/retrieval built in Phase 3 currently only power History Echo matching,
  not Arthur's own article selection. Could be revisited but isn't required.
- An automated **leakage judge** (scoring whether Arthur's entries actually avoid anachronisms,
  beyond just the prompt instruction) is Phase 4, not built yet.
- No hybrid retrieval (keyword + semantic) - History Echo is pure embedding similarity.

## Tech stack

Python 3.11+ (3.13.1 installed), venv named `EchoLedger/` (gitignored). Dependencies: pydantic,
httpx, python-dotenv, tzdata (Windows only), anthropic, fastapi, uvicorn, openai, chromadb,
langgraph, a2a-sdk, sse-starlette, boto3. Dev tools: pytest, ruff, mypy. Ask before adding any
dependency not listed here or in `pyproject.toml`.

## Repo structure (current)

```
echoledger/
├── CLAUDE.md / PROGRESS.md / README.md
├── pyproject.toml / .gitignore / .env.example / .env (gitignored, has real API keys)
├── Dockerfile / .dockerignore / .github/workflows/ci.yml / .github/workflows/eval.yml
├── src/echoledger/
│   ├── config.py  models.py  cli.py
│   ├── storage/      (db.py)
│   ├── sources/      (american_stories.py, rss.py)
│   ├── utils/        (dates.py)
│   ├── llm/          (client.py, arthur.py, news_summary.py, predictions.py)
│   ├── api/          (app.py, views.py, schemas.py)
│   ├── rag/          (embeddings.py, vector_store.py, index.py, echo.py)
│   ├── evals/        (brier.py, leakage_judge.py)
│   ├── guardrails/   (injection.py, copyright.py)
│   └── agents/       (diary_workflow.py, verification_client.py)
├── services/
│   └── verification_agent/  (server.py — standalone A2A server, run separately)
├── tests/
└── data/              # gitignored — downloaded datasets, SQLite db, data/chroma/ vector store
```

## Windows/PowerShell gotcha

Each tool-run PowerShell command starts a **fresh process** — activating the venv in the user's
own terminal does not carry over. Always call the venv's executables by full path directly, e.g.
`D:\EchoLedger\EchoLedger\Scripts\python.exe`, `...\Scripts\pytest.exe`, rather than relying on
`Activate.ps1` having run. (Learned the hard way: a bare `pip install` once silently installed
into the user's global site-packages and upgraded their global `pydantic` 1.10.22 → 2.x, breaking
an unrelated streamlit project — reverted, but be careful.)

## Working conventions

- Explore and plan before writing code; wait for approval.
- Small steps (~30–60 min each); explain what/why/how-to-run after each.
- Explain new concepts in 2–3 plain sentences only when first needed.
- Commit after each working step.
- Update PROGRESS.md at the end of each session.
