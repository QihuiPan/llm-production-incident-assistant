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
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
