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

FROM python:3-slim

COPY --from=builder /src/dist/*.whl /

RUN python -m pip install --no-cache-dir /hugoify*.whl \
 && rm /hugoify*.whl

ENV INPUT_RAWPATH="content/GENERATED"
ENV INPUT_OUTPUTPATH="content/api"
WORKDIR /github/workspace
CMD ["/usr/local/bin/hugoify"]
