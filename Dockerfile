# Reproducible development/runtime image for the KYC capstone (Python 3.12, no third-party deps).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Pinned to the uv version the lockfile was created with.
RUN pip install --no-cache-dir uv==0.12.18

WORKDIR /app

# Dependency layer first so code edits don't invalidate it. The venv lives outside /app so a
# bind-mounted host checkout (possibly with a macOS .venv) never conflicts with it.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked

COPY . .

# Default: the mock enterprise service. It binds to loopback only (by design), so other
# containers must share its network namespace; see docker-compose.yml.
CMD ["uv", "run", "--locked", "python", "tools/runtime.py", "serve", "--port", "8766"]
