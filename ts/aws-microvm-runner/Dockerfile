FROM public.ecr.aws/lambda/microvms:al2023-minimal AS chip-tools

ARG IVERILOG_VERSION=12_0
ARG IVERILOG_SHA256=a68cb1ef7c017ef090ebedb2bc3e39ef90ecc70a3400afb4aa94303bc3beaa7d
ARG YOSYS_VERSION=0.59.1
ARG YOSYS_SHA256=5d442ed3b8ba90147be3939953f5104f019b46dfee6472a904d46b7143fcec1a
ARG SYSTEMC_VERSION=3.0.2
ARG SYSTEMC_SHA256=9b3693ed286aab958b9e5d79bb0ad3bc523bbc46931100553275352038f4a0c4

RUN dnf install -y \
    autoconf \
    bison \
    cmake \
    curl-minimal \
    flex \
    gcc \
    gcc-c++ \
    git \
    gzip \
    gperf \
    libffi-devel \
    make \
    pkgconf-pkg-config \
    readline-devel \
    tcl-devel \
    tar \
    zlib-devel \
  && dnf clean all

WORKDIR /tmp/chip-tools
RUN set -eux; \
    curl -fsSL "https://github.com/steveicarus/iverilog/archive/refs/tags/v${IVERILOG_VERSION}.tar.gz" -o iverilog.tar.gz; \
    echo "${IVERILOG_SHA256}  iverilog.tar.gz" | sha256sum -c -; \
    tar -xzf iverilog.tar.gz; \
    cd "iverilog-${IVERILOG_VERSION}"; \
    sh autoconf.sh; \
    ./configure --prefix=/usr/local; \
    make -j"$(nproc)"; \
    make install

RUN set -eux; \
    curl -fsSL "https://github.com/YosysHQ/yosys/releases/download/v${YOSYS_VERSION}/yosys.tar.gz" -o yosys.tar.gz; \
    echo "${YOSYS_SHA256}  yosys.tar.gz" | sha256sum -c -; \
    mkdir yosys-source; \
    tar -xzf yosys.tar.gz -C yosys-source; \
    cd yosys-source; \
    make -j"$(nproc)" ENABLE_ABC=0 PREFIX=/usr/local; \
    make install ENABLE_ABC=0 PREFIX=/usr/local

RUN set -eux; \
    curl -fsSL "https://github.com/accellera-official/systemc/archive/refs/tags/${SYSTEMC_VERSION}.tar.gz" -o systemc.tar.gz; \
    echo "${SYSTEMC_SHA256}  systemc.tar.gz" | sha256sum -c -; \
    tar -xzf systemc.tar.gz; \
    cmake \
      -S "systemc-${SYSTEMC_VERSION}" \
      -B systemc-build \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DCMAKE_INSTALL_LIBDIR=lib \
      -DBUILD_SHARED_LIBS=ON \
      -DBUILD_TESTING=OFF; \
    cmake --build systemc-build --parallel "$(nproc)"; \
    cmake --install systemc-build; \
    mkdir -p /usr/local/lib/pkgconfig; \
    printf '%s\n' \
      'prefix=/usr/local' \
      'exec_prefix=${prefix}' \
      'libdir=${exec_prefix}/lib' \
      'includedir=${prefix}/include' \
      '' \
      'Name: SystemC' \
      'Description: Accellera SystemC library' \
      "Version: ${SYSTEMC_VERSION}" \
      'Libs: -L${libdir} -lsystemc' \
      'Cflags: -I${includedir}' \
      > /usr/local/lib/pkgconfig/systemc.pc

FROM public.ecr.aws/lambda/microvms:al2023-minimal

RUN dnf install -y \
    gcc \
    gcc-c++ \
    libffi-devel \
    make \
    pkgconf-pkg-config \
    python3 \
    python3-pip \
    readline-devel \
    tar \
    tcl-devel \
    zlib-devel \
    gzip \
    git \
    patch \
    findutils \
    shadow-utils \
    util-linux \
  && dnf clean all

COPY --from=chip-tools /usr/local /usr/local

ENV LD_LIBRARY_PATH=/usr/local/lib \
    PKG_CONFIG_PATH=/usr/local/lib/pkgconfig

RUN python3 -m pip install --no-cache-dir \
    PyYAML==6.0.3 \
    pytest==8.4.1 \
  && iverilog -V 2>&1 | grep -q "Icarus Verilog version 12.0" \
  && yosys -V | grep -q "Yosys 0.59+0" \
  && test "$(pkg-config --modversion systemc)" = "3.0.2" \
  && python3 -c "import pytest, yaml"

USER root
RUN mkdir -p /workspace /testbed /tests /solution /logs /tmp/tb

WORKDIR /opt/code-sandbox-bench
COPY server.py .

EXPOSE 8080
CMD ["python3", "/opt/code-sandbox-bench/server.py"]
