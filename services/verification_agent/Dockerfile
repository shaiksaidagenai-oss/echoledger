# Same base + echoledger package as the main Dockerfile (needed for
# evals/leakage_judge.py, models.py, storage/db.py, config.py) plus this
# service's own code, which isn't part of the installed echoledger package.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

COPY services/ ./services/

EXPOSE 9998
CMD ["python", "-m", "services.verification_agent.server"]
