ARG PYTHON_IMAGE_TAG=3.15-rc
FROM python:${PYTHON_IMAGE_TAG}

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        locales-all \
        ncurses-term \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN printf '%s\n' \
        '#!/bin/sh' \
        'Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &' \
        'DISPLAY=:99 exec "$@"' \
        > /usr/local/bin/run-with-xvfb \
    && chmod 755 /usr/local/bin/run-with-xvfb

ENTRYPOINT ["/usr/local/bin/run-with-xvfb"]
