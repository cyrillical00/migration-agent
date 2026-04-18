FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
RUN pip install --no-cache-dir build && python -m build --wheel --no-isolation .

FROM python:3.12-slim AS runtime

# No shell, non-root user
RUN useradd --create-home --shell /bin/false agent

WORKDIR /app

# Install dependencies first (cache-friendly)
COPY pyproject.toml .
RUN pip install --no-cache-dir . && rm pyproject.toml

# Copy application source
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Switch to non-root
USER agent

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
