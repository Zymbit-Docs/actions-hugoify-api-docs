# Python and dependency versions match the image published 2022-03-16, the
# last one that built, so rebuilding does not change the rendered output.
FROM python:3.10.2-slim AS builder
COPY . /src
WORKDIR /src

# pyproject.toml builds with poetry-core, so pip can build the wheel without
# installing Poetry. (install_hugoify.sh fetched Poetry's retired
# get-poetry.py installer, which no longer works.)
RUN python -m pip wheel --no-cache-dir --no-deps --wheel-dir /src/dist .

FROM python:3.10.2-slim

COPY --from=builder /src/dist/*.whl /

RUN python -m pip install --no-cache-dir /hugoify*.whl \
    "lxml==4.8.0" "ruamel.yaml==0.17.21" "ruamel.yaml.clib==0.2.6" \
 && rm /hugoify*.whl

ENV INPUT_RAWPATH="content/GENERATED"
ENV INPUT_OUTPUTPATH="content/api"
WORKDIR /github/workspace
CMD ["/usr/local/bin/hugoify"]
