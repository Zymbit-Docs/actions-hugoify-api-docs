FROM python:3-alpine AS builder
ADD . /app
WORKDIR /app

RUN pip install --target=/app requests

ENV PYTHONPATH /app
CMD ["/app/main.py"]
