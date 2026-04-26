FROM python:3.14.4-slim

ARG TARGETARCH
ARG GO_VERSION=1.26.2
ARG GO_LINUX_AMD64_SHA256=990e6b4bbba816dc3ee129eaeaf4b42f17c2800b88a2166c265ac1a200262282
ARG GO_LINUX_ARM64_SHA256=c958a1fe1b361391db163a485e21f5f228142d6f8b584f6bef89b26f66dc5b23
ARG GO_BUILD_PARALLELISM=2
ARG OPENSSL_VERSION=3.5.6
ARG OPENSSL_SHA256=deae7c80cba99c4b4f940ecadb3c3338b13cb77418409238e57d7f31f2a3b736
ARG SSLSCAN_VERSION=2.2.0
ARG NUCLEI_VERSION=v3.8.0
ARG SUBFINDER_VERSION=v2.13.0
ARG PD_HTTPX_VERSION=v1.9.0
ARG DNSX_VERSION=v1.2.3
ARG NAABU_VERSION=v2.5.0
ARG KATANA_VERSION=v1.5.0
ARG AMASS_VERSION=v5.1.1
ARG ASSETFINDER_VERSION=v0.1.1
ARG GOBUSTER_VERSION=v3.8.2
ARG FFUF_VERSION=v2.1.0
ARG TESTSSL_VERSION=v3.2.3
ARG SSLYZE_VERSION=6.3.1
ARG WAFW00F_VERSION=2.4.2
ARG RUSTSCAN_VERSION=2.4.1
ARG WPSCAN_VERSION=3.8.28

# Remove dpkg config that prevents man pages from being installed
RUN rm -f /etc/dpkg/dpkg.cfg.d/docker

# Ensure all packages are up to date and install dependencies and tools
RUN apt-get update
RUN apt-get upgrade -y

RUN apt-get install -y  man-db procps net-tools curl wget iputils-ping nmap dnsutils traceroute netcat-traditional \
                        mtr whois tcptraceroute dnsrecon git libnet-ssleay-perl rubygems \
                        libxml-writer-perl libjson-perl ruby-dev build-essential fping python3-requests fierce \
                        dnsenum libcap2-bin sudo gosu groff-base bsdextrautils iptables masscan libpcap-dev \
                        ca-certificates perl zlib1g-dev unzip

# Update the man page database
RUN mandb -c

# Install the official Go toolchain instead of Debian's lagging golang-go package.
WORKDIR /tmp
RUN case "${TARGETARCH}" in \
        amd64) go_sha256="${GO_LINUX_AMD64_SHA256}" ;; \
        arm64) go_sha256="${GO_LINUX_ARM64_SHA256}" ;; \
        *) echo "unsupported Go target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    wget -O go.tar.gz "https://go.dev/dl/go${GO_VERSION}.linux-${TARGETARCH}.tar.gz" && \
    printf "%s  go.tar.gz\n" "${go_sha256}" > go.tar.gz.sha256 && \
    sha256sum -c go.tar.gz.sha256 && \
    tar -C /usr/local -xzf go.tar.gz && \
    rm go.tar.gz go.tar.gz.sha256

# Set GOBIN so all Go binaries install directly into /usr/local/bin,
# world-executable and not owned by root's home directory.
ENV GOBIN=/usr/local/bin
ENV PATH=/usr/local/go/bin:${PATH}
ENV GOMAXPROCS=${GO_BUILD_PARALLELISM}
ENV GOFLAGS=-p=${GO_BUILD_PARALLELISM}

# Install OpenSSL 3.5 LTS from source for current TLS tooling.
WORKDIR /tmp
RUN wget -O openssl.tar.gz "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz" && \
    printf "%s  openssl.tar.gz\n" "${OPENSSL_SHA256}" > openssl.tar.gz.sha256 && \
    sha256sum -c openssl.tar.gz.sha256 && \
    tar xzf openssl.tar.gz && \
    rm openssl.tar.gz openssl.tar.gz.sha256
WORKDIR /tmp/openssl-${OPENSSL_VERSION}
RUN ./config --prefix=/usr/local --openssldir=/usr/local/ssl --libdir=lib shared zlib && \
    make -j"$(nproc)" && \
    make install_sw && \
    ldconfig
WORKDIR /tmp
RUN rm -rf "openssl-${OPENSSL_VERSION}"

# Install sslscan from a pinned upstream release against the current OpenSSL.
WORKDIR /tmp
RUN git clone --depth 1 --branch "${SSLSCAN_VERSION}" https://github.com/rbsec/sslscan.git /tmp/sslscan && \
    make -C /tmp/sslscan -j"$(nproc)" && \
    cp /tmp/sslscan/sslscan /usr/local/bin/sslscan && \
    rm -rf /tmp/sslscan

# Install nuclei.
RUN go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@${NUCLEI_VERSION}

# Install the ProjectDiscovery suite via Go.
# Rename httpx to pd-httpx to avoid colliding with the Python httpx package.
RUN go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@${SUBFINDER_VERSION}
RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@${PD_HTTPX_VERSION} && \
    mv /usr/local/bin/httpx /usr/local/bin/pd-httpx
RUN go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@${DNSX_VERSION}
RUN go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@${NAABU_VERSION}
RUN go install -v github.com/projectdiscovery/katana/cmd/katana@${KATANA_VERSION}
RUN CGO_ENABLED=0 go install -v github.com/owasp-amass/amass/v5/cmd/amass@${AMASS_VERSION}

# Install additional reconnaissance binaries via Go.
RUN go install github.com/tomnomnom/assetfinder@${ASSETFINDER_VERSION}
RUN go install github.com/OJ/gobuster/v3@${GOBUSTER_VERSION}
RUN go install github.com/ffuf/ffuf/v2@${FFUF_VERSION}

# Install the SecLists wordlist collection.
RUN git clone --depth 1 https://github.com/danielmiessler/SecLists.git /usr/share/wordlists/seclists && \
    rm -rf /usr/share/wordlists/seclists/.git

# Install testssl.sh from a pinned upstream release.
WORKDIR /opt/
RUN git clone --depth 1 --branch "${TESTSSL_VERSION}" https://github.com/testssl/testssl.sh.git /opt/testssl.sh && \
    chmod 755 /opt/testssl.sh/testssl.sh && \
    ln -s /opt/testssl.sh/testssl.sh /usr/local/bin/testssl

# Point nuclei at /tmp so it works with read_only: true (tmpfs is mounted there)
ENV NUCLEI_TEMPLATES_DIR=/tmp/nuclei-templates
ENV HOME=/tmp

# Install nikto via git and create a symlink on PATH.
WORKDIR /opt/
RUN git clone https://github.com/sullo/Nikto.git
RUN chmod -R 755 *
RUN ln -s /opt/Nikto/program/nikto.pl /usr/local/bin/nikto

# Upgrade pip to ensure latest versions of dependencies can be installed
RUN pip install --upgrade pip

# Install sslyze via pip.
RUN pip install --upgrade setuptools wheel
RUN pip install --upgrade sslyze==${SSLYZE_VERSION}
RUN pip install --upgrade wafw00f==${WAFW00F_VERSION}

# Install rustscan from the official GitHub releases.
WORKDIR /tmp
RUN wget "https://github.com/bee-san/RustScan/releases/download/${RUSTSCAN_VERSION}/x86_64-linux-rustscan.tar.gz.zip"
RUN unzip x86_64-linux-rustscan.tar.gz.zip && \
    tar xzf x86_64-linux-rustscan.tar.gz && \
    mv rustscan /usr/local/bin/rustscan && \
    rm -rf x86_64-linux-rustscan*

# Install wpscan via RubyGems.
RUN gem install wpscan -v ${WPSCAN_VERSION}

# Install required Python dependencies from requirements.txt
WORKDIR /app
ENV PYTHONPATH=/app

COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt


# Create two unprivileged users:
#   appuser — owns /data and runs Gunicorn (can write SQLite database)
#   scanner — runs all user-submitted commands, no write access to /data
# scanner is also launched with the shared appuser run group so validated
# session workspace files can use group-readable permissions instead of
# world-readable permissions.
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    groupadd -r scanner && useradd -r -g scanner -G appuser -s /usr/sbin/nologin scanner

# Grant raw socket capabilities to tools that require elevated network access,
# so the scanner user can use them without full root privileges.

RUN setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap && \
    setcap cap_net_raw,cap_net_admin+eip /usr/bin/masscan && \
    setcap cap_net_raw,cap_net_admin+eip /usr/local/bin/naabu && \
    echo "appuser ALL=(scanner) NOPASSWD: ALL" >> /etc/sudoers && \
    echo "appuser ALL=(scanner:appuser) NOPASSWD: ALL" >> /etc/sudoers

# Pre-create /data owned by appuser with 700 permissions.
# scanner user cannot write here. The entrypoint re-applies ownership
# after the Docker volume mount potentially resets it.
RUN mkdir -p /data && chown appuser:appuser /data && chmod 700 /data

# Copy entrypoint script — runs as root to fix /data ownership after volume
# mount, then drops to appuser via gosu before starting Gunicorn
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Fallback if built directly with `docker build` outside of Compose (which reads .env).
ARG APP_PORT=8888
EXPOSE ${APP_PORT}

ENTRYPOINT ["/entrypoint.sh"]
