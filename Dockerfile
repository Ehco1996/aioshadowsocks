
FROM python:3.7-alpine

LABEL Name="aio-shadowsocks" Maintainer="Ehco1996"

COPY requirements.txt /tmp/requirements.txt

RUN set -e; \
    apk update \
    && apk add --virtual .build-deps libffi-dev build-base \
    # TODO workaround start
    && apk del libressl-dev \
    && apk add openssl-dev \
    && apk del openssl-dev \
    && apk add libressl-dev \
    # TODO workaround end
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && apk del .build-deps