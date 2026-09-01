FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY api ./api
COPY retrieval ./retrieval
COPY tools ./tools
COPY evals ./evals
COPY workers ./workers
COPY data ./data
COPY prompts ./prompts
COPY infra/postgres ./infra/postgres
RUN pip install --no-cache-dir .

RUN addgroup --system incident && adduser --system --ingroup incident incident \
    && chown -R incident:incident /app
USER incident

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/healthz')"
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
