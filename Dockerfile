# Slim, official Python base image - not a full OS, just enough to run Python.
FROM python:3.11-slim

WORKDIR /app

# Copy only what's needed to install dependencies first. Docker caches each
# step - if these two files don't change, the slow `pip install` step below
# gets skipped on rebuilds even if our actual code changes.
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# Default: serve the read-only API. The CLI (fetch/show/scorecard) is still
# available by overriding the command, e.g. for a scheduled one-off ingest
# task: `docker run <image> echoledger fetch --date ...`.
EXPOSE 8000
CMD ["uvicorn", "echoledger.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
