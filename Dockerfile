FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project --no-dev

COPY main.py ./
COPY static ./static
COPY templates ./templates
RUN mkdir -p /app/data

EXPOSE 5000

CMD ["python", "main.py"]
