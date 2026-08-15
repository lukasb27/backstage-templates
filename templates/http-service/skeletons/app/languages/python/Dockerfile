# -------------------------------------------------
# Base image
# -------------------------------------------------
FROM python:3.13-slim as python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=2.2.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PYSETUP_PATH="/opt/pysetup" \
    POETRY_NO_INTERACTION=1 \
    VENV_PATH="/opt/pysetup/.venv"

ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

# -------------------------------------------------
# Builder stage
# -------------------------------------------------
FROM python-base as builder-base

RUN apt-get update && apt-get install --no-install-recommends -y \
    curl \
    git \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -

WORKDIR $PYSETUP_PATH
COPY poetry.lock pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache \
    poetry install --no-root --without dev

# -------------------------------------------------
# Test image
# -------------------------------------------------
FROM python-base as test

COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH
COPY --from=builder-base $POETRY_HOME $POETRY_HOME

WORKDIR $PYSETUP_PATH
RUN poetry install --without dev --with integ-test --no-root

WORKDIR /app
COPY ./app /app/app
COPY ./integration_tests /app/integration_tests
RUN useradd --create-home --uid 1000 appuser
USER 1000

CMD ["python", "integration_tests/post_report_to_pr.py"]

# -------------------------------------------------
# Development image
# -------------------------------------------------
FROM python-base as development
ENV ENVIRONMENT=dev

COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
RUN poetry install

WORKDIR /app
COPY ./app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]

# -------------------------------------------------
# Production image
# -------------------------------------------------
FROM python-base as production
ENV ENVIRONMENT=prod

COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH
COPY ./app /app/app
WORKDIR /app

# k8s/deployment.yaml sets runAsNonRoot: true — needs a numeric UID (not a
# named USER) for Kubernetes to verify that statically without running the
# container.
RUN useradd --create-home --uid 1000 appuser
USER 1000

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
