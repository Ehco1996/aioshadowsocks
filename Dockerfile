
FROM python:3.8.5-alpine as base
# FROM ehco1996/aioshadowsocks:runtime as base

LABEL Name="aio-shadowsocks" Maintainer="Ehco1996"

COPY README.md poetry.lock pyproject.toml ./
COPY shadowsocks ./shadowsocks

RUN set -e; \
    apk update \
    && apk add --virtual .build-deps libffi-dev build-base \
    # TODO workaround start
    && apk del libressl-dev \
    && apk add openssl-dev \
    && apk del openssl-dev \
    && apk add libressl-dev \
    # TODO workaround end
    && pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi \
    && rm -rf ~/.cache \
    && apk del .build-deps
