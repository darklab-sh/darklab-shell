# syntax=docker/dockerfile:1.7
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

ARG PYTHON_BASE_IMAGE=python:3.14.6-slim
ARG GO_VERSION=1.26.5
ARG GO_LINUX_AMD64_SHA256=5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053
ARG GO_LINUX_ARM64_SHA256=fe4789e92b1f33358680864bbe8704289e7bb5fc207d80623c308935bd696d49
ARG GO_BUILD_PARALLELISM=2
ARG GO_X_CRYPTO_VERSION=v0.52.0
ARG GOSU_VERSION=1.19
ARG OPENSSL_VERSION=3.6.3
ARG OPENSSL_SHA256=243a86649cf6f23eeb6a2ff2456e09e5d77dd9018a54d3d96b0c6bdd6ba6c7f1
ARG SSLSCAN_VERSION=2.2.2
ARG NUCLEI_VERSION=v3.11.0
ARG SUBFINDER_VERSION=v2.14.0
ARG HTTPX_VERSION=v1.10.0
ARG DNSX_VERSION=v1.3.0
ARG NAABU_VERSION=v2.6.1
ARG KATANA_VERSION=v1.6.1
ARG TLSX_VERSION=v1.2.2
ARG CDNCHECK_VERSION=v1.2.45
ARG AMASS_VERSION=v5.1.1
ARG ASSETFINDER_VERSION=v0.1.1
ARG GOBUSTER_VERSION=v3.8.2
ARG FFUF_VERSION=v2.2.1
ARG TRUFFLEHOG_VERSION=v3.95.9
ARG MASSDNS_VERSION=v1.1.0
ARG PUREDNS_VERSION=v2.1.1
ARG TESTSSL_VERSION=v3.2.4
ARG SSLYZE_VERSION=6.3.1
ARG WAFW00F_VERSION=2.4.2
ARG RUSTSCAN_VERSION=2.4.1
ARG RUSTSCAN_LINUX_AMD64_ASSET=x86_64-linux-rustscan.tar.gz.zip
ARG RUSTSCAN_LINUX_AMD64_SHA256=f3a4365d939e3b81f25ba8c37852ce9ac9e938c3cc882c5b3e6fff6152c740be
ARG RUSTSCAN_LINUX_ARM64_ASSET=aarch64-linux-rustscan.zip
ARG RUSTSCAN_LINUX_ARM64_SHA256=4f49103e2dfc9e9709a36da2cd61f1f81613f8d0a203307f750439fc3ce39eae
ARG TCPING_VERSION=v2.8.0
ARG WPSCAN_VERSION=4.0.1
ARG VT_CLI_VERSION=v0.0.0-20260707165039-b4cf77c4340f
ARG IPINFO_CLI_VERSION=ipinfo-3.3.2
ARG URLSCAN_CLI_VERSION=v2026.07.07
ARG CHAOS_CLIENT_VERSION=v0.5.2
ARG SECLISTS_VERSION=2026.1
ARG SECLISTS_COMMIT=190c6f7bd58c847ceadfe57d9853592737f059e8
ARG NIKTO_VERSION=2.6.0
ARG NIKTO_COMMIT=69681e2e4213c15b85a90c53b2169ecb2a88fb01
ARG SETUPTOOLS_VERSION=81.0.0
ARG POSTGRESQL_CLIENT_VERSION=18
ARG POSTGRESQL_APT_KEY_SHA256=0144068502a1eddd2a0280ede10ef607d1ec592ce819940991203941564e8e76
ARG APP_VERSION=2.7.0-rc.3
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG PYTHON_VERSION=3.14.6
ARG PYTHON_BASE_DIGEST=unresolved
ARG PYTHON_BASE_INDEX_DIGEST=unresolved

# The Go builder base is shared by independent tool families. Its module and
# compilation caches stay in builder layers and never enter the runtime image.
FROM ${PYTHON_BASE_IMAGE} AS go-builder-base
ARG TARGETARCH
ARG GO_VERSION
ARG GO_LINUX_AMD64_SHA256
ARG GO_LINUX_ARM64_SHA256
ARG GO_BUILD_PARALLELISM
ARG GO_X_CRYPTO_VERSION
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential ca-certificates git libpcap-dev wget && \
    rm -rf /var/lib/apt/lists/*
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
ENV GOBIN=/out/usr/local/bin
ENV PATH=/usr/local/go/bin:${PATH}
ENV GOMAXPROCS=${GO_BUILD_PARALLELISM}
ENV GOFLAGS=-p=${GO_BUILD_PARALLELISM}
ENV GO_X_CRYPTO_VERSION=${GO_X_CRYPTO_VERSION}
COPY scripts/container/install_go_tool.sh /usr/local/bin/install-go-tool
RUN chmod 0755 /usr/local/bin/install-go-tool && \
    mkdir -p /out/usr/local/bin /out/usr/sbin \
        /out/usr/share/doc/darklab-shell/licenses/go-modules && \
    install -m 0644 /usr/local/go/LICENSE \
        /out/usr/share/doc/darklab-shell/licenses/Go-toolchain.txt

FROM go-builder-base AS go-projectdiscovery
ARG NUCLEI_VERSION
ARG SUBFINDER_VERSION
ARG HTTPX_VERSION
ARG DNSX_VERSION
ARG NAABU_VERSION
ARG KATANA_VERSION
ARG TLSX_VERSION
ARG CDNCHECK_VERSION
ARG CHAOS_CLIENT_VERSION
RUN install-go-tool "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@${NUCLEI_VERSION}"
RUN install-go-tool "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@${SUBFINDER_VERSION}"
RUN install-go-tool "github.com/projectdiscovery/httpx/cmd/httpx@${HTTPX_VERSION}"
RUN install-go-tool "github.com/projectdiscovery/dnsx/cmd/dnsx@${DNSX_VERSION}"
RUN install-go-tool "github.com/projectdiscovery/naabu/v2/cmd/naabu@${NAABU_VERSION}"
RUN install-go-tool "github.com/projectdiscovery/katana/cmd/katana@${KATANA_VERSION}"
RUN install-go-tool "github.com/projectdiscovery/tlsx/cmd/tlsx@${TLSX_VERSION}"
RUN install-go-tool "github.com/projectdiscovery/cdncheck/cmd/cdncheck@${CDNCHECK_VERSION}"
RUN install-go-tool "github.com/projectdiscovery/chaos-client/cmd/chaos@${CHAOS_CLIENT_VERSION}"
RUN projectdiscovery_license=$(find "$(go env GOMODCACHE)/github.com/projectdiscovery" \
        -iname 'LICENSE*' -type f -print -quit) && \
    test -n "$projectdiscovery_license" && \
    install -m 0644 "$projectdiscovery_license" \
        /out/usr/share/doc/darklab-shell/licenses/go-modules/ProjectDiscovery.txt && \
    install -m 0644 \
        "$(go env GOMODCACHE)/golang.org/x/crypto@${GO_X_CRYPTO_VERSION}/LICENSE" \
        /out/usr/share/doc/darklab-shell/licenses/go-modules/golang-x-crypto.txt

FROM go-builder-base AS go-other-tools
ARG GOSU_VERSION
ARG AMASS_VERSION
ARG ASSETFINDER_VERSION
ARG GOBUSTER_VERSION
ARG FFUF_VERSION
ARG TCPING_VERSION
ARG TRUFFLEHOG_VERSION
ARG PUREDNS_VERSION
ARG VT_CLI_VERSION
ARG IPINFO_CLI_VERSION
ARG URLSCAN_CLI_VERSION
RUN CGO_ENABLED=0 install-go-tool "github.com/owasp-amass/amass/v5/cmd/amass@${AMASS_VERSION}"
RUN install-go-tool "github.com/tomnomnom/assetfinder@${ASSETFINDER_VERSION}"
RUN install-go-tool "github.com/OJ/gobuster/v3@${GOBUSTER_VERSION}"
RUN install-go-tool "github.com/ffuf/ffuf/v2@${FFUF_VERSION}"
RUN install-go-tool "github.com/pouriyajamshidi/tcping/v2@${TCPING_VERSION}"
RUN install-go-tool "github.com/d3mondev/puredns/v2@${PUREDNS_VERSION}"
RUN install-go-tool "github.com/VirusTotal/vt-cli/vt@${VT_CLI_VERSION}"
RUN install-go-tool "github.com/ipinfo/cli/ipinfo@${IPINFO_CLI_VERSION}"
RUN install-go-tool "github.com/urlscan/urlscan-cli@${URLSCAN_CLI_VERSION}"
RUN git clone --depth 1 --branch "${GOSU_VERSION}" \
        https://github.com/tianon/gosu.git /tmp/gosu && \
    go -C /tmp/gosu build -trimpath -o /out/usr/sbin/gosu . && \
    install -m 0644 /tmp/gosu/LICENSE \
        /out/usr/share/doc/darklab-shell/licenses/gosu.txt && \
    /out/usr/sbin/gosu --version && \
    rm -rf /tmp/gosu
# hadolint ignore=DL3062
RUN git clone --depth 1 --branch "${TRUFFLEHOG_VERSION}" \
        https://github.com/trufflesecurity/trufflehog.git /tmp/trufflehog && \
    go -C /tmp/trufflehog install && \
    install -m 0644 /tmp/trufflehog/LICENSE \
        /out/usr/share/doc/darklab-shell/licenses/TruffleHog.txt && \
    rm -rf /tmp/trufflehog
RUN amass_license=$(find "$(go env GOMODCACHE)/github.com/owasp-amass" \
        -iname 'LICENSE*' -type f -print -quit) && \
    assetfinder_license=$(find "$(go env GOMODCACHE)/github.com/tomnomnom" \
        -iname 'LICENSE*' -type f -print -quit) && \
    gobuster_license=$(find "$(go env GOMODCACHE)/github.com/!o!j" \
        -iname 'LICENSE*' -type f -print -quit) && \
    ffuf_license=$(find "$(go env GOMODCACHE)/github.com/ffuf" \
        -iname 'LICENSE*' -type f -print -quit) && \
    tcping_license=$(find "$(go env GOMODCACHE)/github.com/pouriyajamshidi" \
        -iname 'LICENSE*' -type f -print -quit) && \
    puredns_license=$(find "$(go env GOMODCACHE)/github.com/d3mondev" \
        -iname 'LICENSE*' -type f -print -quit) && \
    vt_license=$(find "$(go env GOMODCACHE)/github.com/!virus!total" \
        -path '*/vt-cli@*/LICENSE*' -type f -print -quit) && \
    ipinfo_license=$(find "$(go env GOMODCACHE)/github.com/ipinfo" \
        -iname 'LICENSE*' -type f -print -quit) && \
    urlscan_license=$(find "$(go env GOMODCACHE)/github.com/urlscan" \
        -iname 'LICENSE*' -type f -print -quit) && \
    test -n "$amass_license" && test -n "$assetfinder_license" && \
    test -n "$gobuster_license" && test -n "$ffuf_license" && \
    test -n "$tcping_license" && test -n "$puredns_license" && \
    test -n "$vt_license" && test -n "$ipinfo_license" && \
    test -n "$urlscan_license" && \
    install -m 0644 "$amass_license" \
        /out/usr/share/doc/darklab-shell/licenses/go-modules/OWASP-Amass.txt && \
    install -m 0644 "$assetfinder_license" \
        /out/usr/share/doc/darklab-shell/licenses/go-modules/assetfinder.txt && \
    install -m 0644 "$gobuster_license" \
        /out/usr/share/doc/darklab-shell/licenses/go-modules/gobuster.txt && \
    install -m 0644 "$ffuf_license" \
        /out/usr/share/doc/darklab-shell/licenses/go-modules/ffuf.txt && \
    install -m 0644 "$tcping_license" \
        /out/usr/share/doc/darklab-shell/licenses/go-modules/tcping.txt && \
    install -m 0644 "$puredns_license" \
        /out/usr/share/doc/darklab-shell/licenses/go-modules/puredns.txt && \
    install -m 0644 "$vt_license" \
        /out/usr/share/doc/darklab-shell/licenses/VirusTotal-vt-cli.txt && \
    install -m 0644 "$ipinfo_license" \
        /out/usr/share/doc/darklab-shell/licenses/IPinfo-cli.txt && \
    install -m 0644 "$urlscan_license" \
        /out/usr/share/doc/darklab-shell/licenses/urlscan-cli.txt

FROM ${PYTHON_BASE_IMAGE} AS native-tools
ARG OPENSSL_VERSION
ARG OPENSSL_SHA256
ARG SSLSCAN_VERSION
ARG MASSDNS_VERSION
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential ca-certificates git libpcap-dev wget zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*
RUN mkdir -p /out/usr/local/bin /out/usr/share/doc/darklab-shell/licenses
WORKDIR /tmp
RUN wget -O openssl.tar.gz \
        "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz" && \
    printf "%s  openssl.tar.gz\n" "${OPENSSL_SHA256}" > openssl.tar.gz.sha256 && \
    sha256sum -c openssl.tar.gz.sha256 && \
    tar xzf openssl.tar.gz && \
    rm openssl.tar.gz openssl.tar.gz.sha256
WORKDIR /tmp/openssl-${OPENSSL_VERSION}
RUN multiarch=$(gcc -print-multiarch) && \
    ./config --prefix=/usr/local --openssldir=/usr/local/ssl \
        --libdir="lib/${multiarch}" shared zlib && \
    make -j"$(nproc)" build_sw && \
    make install_sw install_ssldirs && \
    ldconfig && \
    mkdir -p "/out/usr/local/lib/${multiarch}" && \
    cp -a /usr/local/bin/openssl /out/usr/local/bin/ && \
    cp -a "/usr/local/lib/${multiarch}/libcrypto.so"* \
        "/usr/local/lib/${multiarch}/libssl.so"* \
        "/out/usr/local/lib/${multiarch}/" && \
    cp -a /usr/local/ssl /out/usr/local/ && \
    install -m 0644 LICENSE.txt \
        /out/usr/share/doc/darklab-shell/licenses/OpenSSL.txt
RUN multiarch=$(gcc -print-multiarch) && \
    test -d "/usr/local/lib/${multiarch}/engines-3" && \
    test -d "/usr/local/lib/${multiarch}/ossl-modules" && \
    mkdir -p "/out/usr/local/lib/${multiarch}" && \
    cp -a "/usr/local/lib/${multiarch}/engines-3" \
        "/usr/local/lib/${multiarch}/ossl-modules" \
        "/out/usr/local/lib/${multiarch}/"
WORKDIR /tmp
RUN git clone --depth 1 --branch "${SSLSCAN_VERSION}" \
        https://github.com/rbsec/sslscan.git /tmp/sslscan && \
    make -C /tmp/sslscan -j"$(nproc)" && \
    install -m 0755 /tmp/sslscan/sslscan /out/usr/local/bin/sslscan && \
    install -m 0644 /tmp/sslscan/LICENSE \
        /out/usr/share/doc/darklab-shell/licenses/sslscan.txt && \
    rm -rf /tmp/sslscan
RUN git clone --depth 1 --branch "${MASSDNS_VERSION}" \
        https://github.com/blechschmidt/massdns.git /tmp/massdns && \
    make -C /tmp/massdns -j"$(nproc)" && \
    install -m 0755 /tmp/massdns/bin/massdns /out/usr/local/bin/massdns && \
    install -m 0644 /tmp/massdns/LICENSE \
        /out/usr/share/doc/darklab-shell/licenses/massdns.txt && \
    rm -rf /tmp/massdns

FROM ${PYTHON_BASE_IMAGE} AS wordlist-assets
ARG SECLISTS_VERSION
ARG SECLISTS_COMMIT
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates git && \
    rm -rf /var/lib/apt/lists/*
RUN mkdir -p /usr/share/wordlists && \
    git clone --depth 1 --branch "${SECLISTS_VERSION}" \
        https://github.com/danielmiessler/SecLists.git \
        /usr/share/wordlists/seclists && \
    test "$(git -C /usr/share/wordlists/seclists rev-parse HEAD)" = \
        "${SECLISTS_COMMIT}" && \
    rm -rf /usr/share/wordlists/seclists/.git

FROM ${PYTHON_BASE_IMAGE} AS script-assets
ARG NIKTO_VERSION
ARG NIKTO_COMMIT
ARG TESTSSL_VERSION
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates git && \
    rm -rf /var/lib/apt/lists/*
RUN mkdir -p /out/opt && \
    git clone --depth 1 --branch "${NIKTO_VERSION}" \
        https://github.com/sullo/Nikto.git /out/opt/Nikto && \
    test "$(git -C /out/opt/Nikto rev-parse HEAD)" = "${NIKTO_COMMIT}" && \
    rm -rf /out/opt/Nikto/.git && \
    chmod -R 0755 /out/opt/Nikto
RUN git clone --depth 1 --branch "${TESTSSL_VERSION}" \
        https://github.com/testssl/testssl.sh.git /out/opt/testssl.sh && \
    rm -rf /out/opt/testssl.sh/.git && \
    chmod 0755 /out/opt/testssl.sh/testssl.sh && \
    mkdir -p /out/usr/local/bin && \
    ln -s /opt/Nikto/program/nikto.pl /out/usr/local/bin/nikto && \
    ln -s /opt/testssl.sh/testssl.sh /out/usr/local/bin/testssl

FROM ${PYTHON_BASE_IMAGE} AS rustscan-asset
ARG TARGETARCH
ARG RUSTSCAN_VERSION
ARG RUSTSCAN_LINUX_AMD64_ASSET
ARG RUSTSCAN_LINUX_AMD64_SHA256
ARG RUSTSCAN_LINUX_ARM64_ASSET
ARG RUSTSCAN_LINUX_ARM64_SHA256
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl unzip && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /tmp
RUN case "${TARGETARCH}" in \
        amd64) rustscan_asset="${RUSTSCAN_LINUX_AMD64_ASSET}"; rustscan_sha256="${RUSTSCAN_LINUX_AMD64_SHA256}" ;; \
        arm64) rustscan_asset="${RUSTSCAN_LINUX_ARM64_ASSET}"; rustscan_sha256="${RUSTSCAN_LINUX_ARM64_SHA256}" ;; \
        *) echo "unsupported RustScan target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    curl --fail --location \
        --connect-timeout 15 \
        --max-time 90 \
        --retry 4 \
        --retry-delay 3 \
        --retry-all-errors \
        --output rustscan.zip \
        "https://github.com/bee-san/RustScan/releases/download/${RUSTSCAN_VERSION}/${rustscan_asset}" && \
    printf "%s  rustscan.zip\n" "${rustscan_sha256}" > rustscan.zip.sha256 && \
    sha256sum -c rustscan.zip.sha256 && \
    unzip rustscan.zip && \
    if [ "${TARGETARCH}" = "amd64" ]; then \
        tar xzf x86_64-linux-rustscan.tar.gz; \
    fi && \
    mkdir -p /out/usr/local/bin && \
    install -m 0755 rustscan /out/usr/local/bin/rustscan

FROM ${PYTHON_BASE_IMAGE} AS ruby-tools
ARG WPSCAN_VERSION
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential ruby-dev rubygems zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*
RUN gem install wpscan -v "${WPSCAN_VERSION}" && \
    mkdir -p /out/var/lib /out/usr/local/bin && \
    cp -a /var/lib/gems /out/var/lib/ && \
    cp -a /usr/local/bin/wpscan /out/usr/local/bin/

FROM ${PYTHON_BASE_IMAGE} AS runtime
ARG TARGETARCH
ARG PYTHON_BASE_DIGEST
ARG PYTHON_BASE_INDEX_DIGEST
ARG APP_VERSION
ARG VCS_REF
ARG BUILD_DATE
ARG PYTHON_VERSION
ARG SETUPTOOLS_VERSION
ARG SSLYZE_VERSION
ARG WAFW00F_VERSION
ARG POSTGRESQL_CLIENT_VERSION
ARG POSTGRESQL_APT_KEY_SHA256

# Install runtime packages only. Compilers and development headers remain in
# builder stages, and apt indexes are not retained in the release image.
RUN rm -f /etc/dpkg/dpkg.cfg.d/docker && \
    apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    install -d /usr/share/postgresql-common/pgdg && \
    curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc && \
    printf "%s  %s\n" "${POSTGRESQL_APT_KEY_SHA256}" \
        /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        > /tmp/postgresql-apt-key.sha256 && \
    sha256sum -c /tmp/postgresql-apt-key.sha256 && \
    rm /tmp/postgresql-apt-key.sha256 && \
    . /etc/os-release && \
    architecture=$(dpkg --print-architecture) && \
    printf "Types: deb\nURIs: https://apt.postgresql.org/pub/repos/apt\nSuites: %s-pgdg\nArchitectures: %s\nComponents: main\nSigned-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc\n" \
        "$VERSION_CODENAME" "$architecture" \
        > /etc/apt/sources.list.d/pgdg.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        man-db procps net-tools curl wget iputils-ping nmap dnsutils traceroute \
        netcat-traditional mtr whois tcptraceroute dnsrecon git \
        libnet-ssleay-perl rubygems ruby libxml-writer-perl libjson-perl fping \
        python3-requests fierce dnsenum libcap2-bin sudo groff-base \
        bsdextrautils iptables masscan libpcap0.8 ca-certificates perl \
        postgresql-client-${POSTGRESQL_CLIENT_VERSION} zlib1g unzip \
        inetutils-telnet httping && \
    rm -rf /var/lib/apt/lists/*
RUN mkdir -p /usr/share/doc/darklab-shell/licenses

COPY --from=go-projectdiscovery /out/ /
COPY --from=go-other-tools /out/ /
COPY --from=native-tools /out/ /
COPY --from=wordlist-assets /usr/share/wordlists/seclists/ /usr/share/wordlists/seclists/
COPY --from=script-assets /out/ /
COPY --from=rustscan-asset /out/ /
COPY --from=ruby-tools /out/ /

RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/local/ssl/cert.pem && \
    ln -sfn /etc/ssl/certs /usr/local/ssl/certs && \
    ldconfig && \
    mandb -c && \
    ruby -rjson -e '\
      specs = Gem::Specification.to_a.map { |spec| { \
        "name" => spec.name, \
        "version" => spec.version.to_s, \
        "licenses" => spec.licenses.map(&:to_s).sort, \
        "homepage" => spec.homepage.to_s, \
        "default_gem" => spec.default_gem? \
      } }.sort_by { |spec| [spec["name"], spec["version"], spec["default_gem"].to_s] }; \
      missing = specs.select { |spec| spec["licenses"].empty? }; \
      raise "RubyGems missing license metadata: #{missing.map { |spec| spec["name"] }.join(", ")}" unless missing.empty?; \
      payload = { "schema_version" => 1, "gems" => specs }; \
      File.write("/usr/share/doc/darklab-shell/wpscan-ruby-gems.json", JSON.pretty_generate(payload))'

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV NUCLEI_TEMPLATES_DIR=/tmp/nuclei-templates
ENV HOME=/tmp
ENV PYTHONPATH=/app
WORKDIR /app

# Install Python runtime dependencies after the toolchain layers so ordinary
# application changes don't invalidate scanner construction.
RUN pip install --upgrade pip && \
    pip install --upgrade setuptools==${SETUPTOOLS_VERSION} wheel && \
    pip install --upgrade sslyze==${SSLYZE_VERSION} && \
    pip install --upgrade wafw00f==${WAFW00F_VERSION}
COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    pip install --no-cache-dir setuptools==${SETUPTOOLS_VERSION} shodan greynoise && \
    rm -f /tmp/requirements.txt

# Create two unprivileged users:
#   appuser — owns /data and runs Gunicorn (can write SQLite database)
#   scanner — runs all user-submitted commands, no write access to /data
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    groupadd -r scanner && useradd -r -g scanner -G appuser -s /usr/sbin/nologin scanner

# Grant raw socket capabilities to tools that require elevated network access.
RUN setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap && \
    setcap cap_net_raw,cap_net_admin+eip /usr/bin/masscan && \
    setcap cap_net_raw,cap_net_admin+eip /usr/local/bin/naabu && \
    echo "appuser ALL=(scanner) NOPASSWD: SETENV: ALL" >> /etc/sudoers && \
    echo "appuser ALL=(scanner:appuser) NOPASSWD: SETENV: ALL" >> /etc/sudoers

RUN mkdir -p /data && chown appuser:appuser /data && chmod 700 /data

# Development Compose mounts ./app over this copy; release images run directly
# from the checked-in application tree.
COPY app/ /app/
COPY scripts/operations/backup_system.py scripts/operations/migrate_sqlite_to_postgres.py scripts/operations/restore_system.py /app/tools/

# Keep the reviewed redistribution inventory and notices with the image.
COPY LICENSE /usr/share/doc/darklab-shell/LICENSE
COPY deploy/THIRD_PARTY_NOTICES.txt deploy/container-licenses.json /usr/share/doc/darklab-shell/
COPY deploy/third-party-licenses/ /usr/share/doc/darklab-shell/licenses/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ARG APP_PORT=8888
EXPOSE ${APP_PORT}
ENTRYPOINT ["/entrypoint.sh"]

# Keep volatile release metadata last so changing version, revision, or build date
# doesn't invalidate any filesystem or runtime-configuration layer above it.
LABEL org.opencontainers.image.title="darklab_shell" \
      org.opencontainers.image.description="Self-hosted browser shell for network diagnostics and security recon" \
      org.opencontainers.image.source="https://gitlab.com/darklab.sh/darklab_shell" \
      org.opencontainers.image.url="https://shell.darklab.sh/" \
      org.opencontainers.image.vendor="darklab.sh" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      sh.darklab.app.name="darklab_shell" \
      sh.darklab.app.version="${APP_VERSION}" \
      sh.darklab.git.revision="${VCS_REF}" \
      sh.darklab.python.version="${PYTHON_VERSION}" \
      sh.darklab.python.base.digest="${PYTHON_BASE_DIGEST}" \
      sh.darklab.python.base.index.digest="${PYTHON_BASE_INDEX_DIGEST}" \
      sh.darklab.image.architecture="${TARGETARCH}"
