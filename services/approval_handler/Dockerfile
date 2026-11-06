# Same base + minimal deps pattern as the other two services, running as
# an ECS Fargate service with a public IP instead of Lambda - Lambda's
# public invocation (Function URL and API Gateway both) turned out to be
# blocked by an organizational restriction, see core.py's docstring.
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn pydantic python-dotenv boto3

COPY src/echoledger ./src/echoledger/
COPY services/ ./services/
ENV PYTHONPATH=/app/src:/app

EXPOSE 8080
CMD ["uvicorn", "services.approval_handler.app:app", "--host", "0.0.0.0", "--port", "8080"]
