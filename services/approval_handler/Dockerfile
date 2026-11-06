# This function only needs a handful of echoledger's modules
# (approval_tokens, config, storage/db, models), not the full package's
# heavy dependency tree (chromadb, langgraph, a2a-sdk, anthropic, openai...)
# - install just what those modules actually import, directly.
FROM public.ecr.aws/lambda/python:3.11

RUN pip install pydantic python-dotenv boto3

COPY src/echoledger ${LAMBDA_TASK_ROOT}/echoledger/
COPY services/ ${LAMBDA_TASK_ROOT}/services/

CMD ["services.approval_handler.handler.handler"]
