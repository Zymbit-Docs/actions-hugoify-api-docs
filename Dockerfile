FROM python:3 AS builder
COPY . /app
WORKDIR /app

ENV PATH="/etc/poetry/bin:/app/hugoify:${PATH}"
ENV PYTHONPATH /app/hugoify:/app
ENV POETRY_HOME=/etc/poetry

RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py --output /tmp/get-poetry.py \
    && python /tmp/get-poetry.py > /dev/null \
    && poetry config virtualenvs.in-project true

RUN poetry install

# RUN pip install --target=/app --no-cache-dir ruamel.yaml lxml

# CMD ["/app/hugoify/main.py"]
ENV INPUT_RAWPATH="input" \
    INPUT_OUTPUTPATH="output"
# WORKDIR /github/workspace
ENTRYPOINT ["/etc/poetry/bin/poetry", "run", "hugoify"]
