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
RUN pip install --no-cache-dir .

RUN addgroup --system incident && adduser --system --ingroup incident incident \
    && chown -R incident:incident /app
USER incident

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
