FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY ghosttrack ./ghosttrack
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 ghosttrack
USER ghosttrack
WORKDIR /home/ghosttrack
ENTRYPOINT ["ghosttrack"]
