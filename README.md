# EchoLedger — "Then & Now"

A daily, AI-generated, human-approved publication comparing today's news with the news from
exactly 100 years ago.

Status: **Phase 1** — collecting raw data (US newspapers from 1926 via the "American Stories"
dataset, today's news via RSS) into a local SQLite database, with a basic CLI, tests, and CI.

See [CLAUDE.md](CLAUDE.md) for project rules/architecture and [PROGRESS.md](PROGRESS.md) for
session-by-session status.

## Setup

```powershell
python -m venv EchoLedger
.\EchoLedger\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Usage (coming online during Phase 1)

```
echoledger fetch --date YYYY-MM-DD
echoledger show --date YYYY-MM-DD
```
