# AWS's own Lambda base image - same shared echoledger package as the other
# two services (needs storage/db.py, config.py, approval_tokens.py), plus
# this handler's own code.
FROM public.ecr.aws/lambda/python:3.11

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install .

COPY services/ ${LAMBDA_TASK_ROOT}/services/

CMD ["services.approval_handler.handler.handler"]
