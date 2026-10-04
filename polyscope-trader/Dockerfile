FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY templates ./templates
RUN pip install --no-cache-dir .

ENV POLYSCOPE_DB_PATH=/data/polyscope.db
VOLUME /data
