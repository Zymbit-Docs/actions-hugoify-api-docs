FROM python:3-slim AS builder
ADD . /app
WORKDIR /app

RUN pip install --target=/app ruamel.yaml

ENV PYTHONPATH /app
CMD ["/app/main.py"]
