# Build stage: uv resolves the locked dependency set into a self-contained
# virtualenv. Nothing from this stage's tooling (uv, caches) reaches the
# runtime image.
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS build
COPY --from=ghcr.io/astral-sh/uv:0.10@sha256:72ab0aeb448090480ccabb99fb5f52b0dc3c71923bffb5e2e26517a1c27b7fec /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first: this layer only rebuilds when the lockfile changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY pyproject.toml README.md LICENSE uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# Runtime: the digest-pinned interpreter, the built virtualenv, and nothing
# else. No package installer, no build tooling, a fixed non-root UID, and a
# root filesystem that works read-only (all writes go to the output mount).
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

RUN /usr/local/bin/python -m pip uninstall --yes pip \
    && rm -r /usr/local/lib/python3.14/ensurepip \
    && useradd --uid 10001 --create-home appuser

COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
WORKDIR /app

# All behavior comes from PDFOPS_* environment variables - no arguments, no CMD.
ENTRYPOINT ["python", "-m", "pdf_ops"]
