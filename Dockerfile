FROM python:3.9-slim-buster as base
LABEL Name="aio-shadowsocks" Maintainer="Ehco1996"

COPY . .

# Note to install cryptography check this  https://github.com/pyca/cryptography/blob/1340c00/docs/installation.rst#building-cryptography-on-linux
RUN set -e; \
    # apk update \
    # && apk add gcc musl-dev python3-dev libffi-dev openssl-dev \
    pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi \
    && rm -rf ~/.cache

CMD ["aioss", "run_ss_server"]