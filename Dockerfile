# =============================================================================
# Dockerfile — the pipeline application container.
#
# This image contains the Python code (lake/, warehouse/, src/) and its
# dependencies. It does NOT contain PostgreSQL — that's a separate service
# in docker-compose.yml. Keeping them as separate containers (rather than
# one container running both) is standard practice: each service can be
# started, stopped, scaled, and versioned independently, and it mirrors
# how you'd deploy this for real (an app container talking to a managed
# database, not bundled together).
# =============================================================================

FROM python:3.12-slim

# Prevents Python from writing .pyc files and buffering stdout — the
# second one matters a lot here: without it, log lines can appear
# out of order or get lost when you run `docker compose logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements first, install, THEN copy the rest of the code.
# Docker caches each layer — as long as requirements.txt doesn't change,
# this dependency layer is reused on every rebuild instead of
# reinstalling everything from scratch each time you edit a .py file.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No CMD here on purpose — docker-compose.yml specifies which pipeline
# stage to run (generate / ingest / load / all three), so this image
# stays reusable for any of them rather than baking in one fixed command.
