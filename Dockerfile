FROM python:3 AS builder
COPY . /src
WORKDIR /src

ENV PATH="/etc/poetry/bin:/hugoify:${PATH}"
ENV PYTHONPATH /src
ENV POETRY_HOME=/etc/poetry

RUN ./install_hugoify.sh

# RUN pip install --target=/app --no-cache-dir ruamel.yaml lxml

# CMD ["/app/hugoify/main.py"]
# WORKDIR /github/workspace
# ENTRYPOINT ["/app/bin/hugoify"]

FROM python:3

COPY --from=builder /src/dist/*.whl /

RUN pip install /hugoify*.whl

ENV INPUT_RAWPATH="content/GENERATED"
ENV INPUT_OUTPUTPATH="content/api"
WORKDIR /github/workspace
ENTRYPOINT ["/usr/local/bin/hugoify"]
