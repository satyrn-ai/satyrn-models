ARG PYTHON_IMAGE_TAG=3.15

FROM node:24-trixie-slim AS pi
RUN npm install --global --prefix /opt/pi --ignore-scripts @earendil-works/pi-coding-agent@1.5.2

FROM python:${PYTHON_IMAGE_TAG}
RUN python3 -m compileall -q /usr/local/lib/python3.15
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/*

COPY --from=pi /usr/local/bin/node /usr/local/bin/node
COPY --from=pi /opt/pi /opt/pi

ENV PATH=/opt/pi/bin:$PATH
RUN node --version && pi --version
WORKDIR /workspace
