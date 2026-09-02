# Deliberately simple starter image. Planned hardening: pinned-by-digest base,
# multi-stage uv build (no pip/build tooling in the runtime layer), verified
# read-only-rootfs posture.
FROM python:3.14-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

# Non-root from day one; fixed UID so volume-permission guidance stays concrete.
RUN useradd --uid 10001 --create-home appuser
USER 10001

# All behavior comes from PDFOPS_* environment variables - no arguments, no CMD.
ENTRYPOINT ["python", "-m", "pdf_ops"]
