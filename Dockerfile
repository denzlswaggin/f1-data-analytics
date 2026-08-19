# Container image for the F1 data platform: ingestion + dbt + analytics CLIs.
#
#   docker build -t f1-platform .
#   docker run --rm f1-platform backfill --season 2024            # ingestion CLI
#   docker run --rm --entrypoint f1-analytics f1-platform ratings # analytics CLI
#   docker run --rm --entrypoint dbt f1-platform build \
#       --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install core first, then the dbt extra in a separate resolve — installing them
# together overflows pip's backtracking resolver (see CLAUDE.md). psycopg2-binary,
# pyarrow, duckdb and numpy all ship manylinux wheels, so no build toolchain.
COPY pyproject.toml README.md LICENSE ./
COPY ingestion ./ingestion
COPY analytics ./analytics
COPY orchestration ./orchestration
COPY warehouse ./warehouse
RUN pip install . && pip install ".[dbt]"

# Bake the dbt packages in (they're regenerated, not in the build context).
RUN dbt deps --project-dir warehouse/dbt --profiles-dir warehouse/dbt

# Run as a non-root user.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

# Default to the ingestion CLI; override --entrypoint for analytics / dbt / dagster.
ENTRYPOINT ["f1-ingest"]
CMD ["--help"]
