FROM ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git pkg-config ca-certificates libasound2-dev \
    libfreetype6-dev libfontconfig1-dev libx11-dev libxext-dev libxinerama-dev \
    libxrandr-dev libxcursor-dev libxrender-dev libxcomposite-dev libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*
