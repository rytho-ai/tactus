FROM ghcr.io/astral-sh/uv@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff AS uv
FROM ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git build-essential cmake libfontconfig1 libfreetype6 \
    && rm -rf /var/lib/apt/lists/*
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_PYTHON_PREFERENCE=only-managed
RUN uv python install 3.12.11
COPY vendor/tactus /project/vendor/tactus
COPY work /project/work
WORKDIR /project/work
RUN uv sync --frozen --python 3.12.11 --no-dev
RUN ln -s /trial/tools /project/work/tools
COPY run_isolated.py /project/run_isolated.py
RUN dpkg-query -W > /project/system-packages.txt
ENV TACTUS_POOL=/trial/pool
CMD ["uv", "run", "--frozen", "--offline", "python", "/project/run_isolated.py"]
