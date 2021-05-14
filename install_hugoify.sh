#!/usr/bin/env bash

# Install and configure Poetry
curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py --output /tmp/get-poetry.py
python /tmp/get-poetry.py > /dev/null
poetry config virtualenvs.in-project true

# Build Hugoify
poetry install
poetry build -f wheel

# # Install Hugoify in the environment
# cd ~
# python -m pip install ./dist/hugoify*.whl
