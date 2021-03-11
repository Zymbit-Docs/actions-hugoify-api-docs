FROM python:3-slim AS builder
COPY . /app
WORKDIR /app

RUN pip install --target=/app --no-cache-dir ruamel.yaml

ENV PYTHONPATH /app
CMD ["/app/main.py"]
