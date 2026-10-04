# INIS — image de production (§4.3).
#
# Séparée de `docker/Dockerfile.dev` : ici aucune dépendance de build (gcc) n'est
# conservée, les sources ne sont pas montées et le processus tourne sous un
# utilisateur non privilégié.
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# `pyproject.toml` + sources : l'installation est faite dans un virtualenv que
# l'étage final recopie, sans compilateur ni cache pip.
COPY pyproject.toml ./
COPY app/ ./app/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Migrations et configuration runtime : l'API les lit au démarrage
# (§41.14 — `alembic upgrade head` en job de déploiement).
COPY alembic.ini ./alembic.ini
COPY migrations/ ./migrations/
COPY configs/ ./configs/

# Utilisateur non privilégié (uid 10001) : l'image ne tourne pas en root.
RUN useradd --create-home --uid 10001 inis \
    && chown -R inis:inis /app
USER inis

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
