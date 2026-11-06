FROM python:3.12-alpine

ARG BUILD_VERSION=2.0.1
ARG BUILD_ARCH=amd64
LABEL io.hass.version="$BUILD_VERSION" \
      io.hass.type="app" \
      io.hass.arch="$BUILD_ARCH"

RUN apk add --no-cache openssh-client \
    && pip install --no-cache-dir "aiohttp==3.12.15"

WORKDIR /opt/shwm
COPY app.py tv_capture.py pairing.py bootstrap.py runtime_status.py ./
CMD ["python", "-u", "app.py"]
