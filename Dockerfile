FROM python:3.11-bookworm AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    # install calibre system dependencies
    xdg-utils \
    xz-utils \
    libopengl0 \
    libegl1 \
    libxcb-cursor0 \
    libfreetype6 && \
    apt-get remove --purge --auto-remove -y && \
    apt-get clean && \
    rm -rf \
    /tmp/* \
    /var/lib/apt/lists/* \
    /var/tmp/*

ENV CALIBRE_CONFIG_DIRECTORY=/app/.calibre \
    CALIBRE_TEMP_DIR=/tmp \
    CALIBRE_CACHE_DIRECTORY=/tmp

RUN useradd -s /bin/bash calibre -u 1000 && \
    mkdir -p ${CALIBRE_CONFIG_DIRECTORY} && \
    chown -R 1000:1000 ${CALIBRE_CONFIG_DIRECTORY}

EXPOSE 80 443

FROM base AS app
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app
WORKDIR /app
CMD ["python", "app.py", "--bind", "unix:/tmp/gunicorn.sock"]

FROM base AS calibre_builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget && \
    wget -nv -O- \
    https://download.calibre-ebook.com/linux-installer.sh | sh /dev/stdin install_dir=/opt && \
    apt-get remove --purge --auto-remove -y && \
    apt-get clean && \
    rm -rf \
    /tmp/* \
    /var/lib/apt/lists/* \
    /var/tmp/*


FROM calibre_builder AS calibre
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app
WORKDIR /app
