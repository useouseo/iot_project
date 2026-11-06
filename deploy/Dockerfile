# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS wheels
WORKDIR /build
COPY requirements.txt .
# Optional CA secret is used only in managed test environments; never stored in layers.
RUN --mount=type=secret,id=system_ca \
    if [ -f /run/secrets/system_ca ]; then export PIP_CERT=/run/secrets/system_ca; fi; \
    apt-get update && apt-get install -y --no-install-recommends gcc libmariadb-dev \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libmariadb3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home restflow
WORKDIR /app
COPY --from=wheels /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels
COPY --chown=restflow:restflow server.py .
COPY --chown=restflow:restflow web ./web
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER restflow
EXPOSE 8000
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8000"]
