# Slim, official Python base image - not a full OS, just enough to run Python.
FROM python:3.11-slim

WORKDIR /app

# Copy only what's needed to install dependencies first. Docker caches each
# step - if these two files don't change, the slow `pip install` step below
# gets skipped on rebuilds even if our actual code changes.
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

ENTRYPOINT ["echoledger"]
