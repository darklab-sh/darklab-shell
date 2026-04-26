FROM python:3.14.4-slim

# Remove dpkg config that prevents man pages from being installed
RUN rm -f /etc/dpkg/dpkg.cfg.d/docker

# Ensure all packages are up to date and install dependencies and tools
RUN apt-get update
RUN apt-get upgrade -y

RUN apt-get install -y  man-db procps net-tools curl wget iputils-ping nmap dnsutils traceroute netcat-traditional \
                        mtr whois tcptraceroute testssl.sh dnsrecon git libnet-ssleay-perl golang-go rubygems \
                        libxml-writer-perl libjson-perl ruby-dev build-essential fping python3-requests fierce \
                        dnsenum libcap2-bin sudo gosu groff-base bsdextrautils iptables sslscan wafw00f masscan libpcap-dev

# Update the man page database
RUN mandb -c

# Set GOBIN so all Go binaries install directly into /usr/local/bin,
# world-executable and not owned by root's home directory.
ENV GOBIN=/usr/local/bin

# Install nuclei.
RUN go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@v3.8.0

# Install the ProjectDiscovery suite via Go.
# Rename httpx to pd-httpx to avoid colliding with the Python httpx package.
RUN go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@v2.13.0
RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@v1.9.0 && \
    mv /usr/local/bin/httpx /usr/local/bin/pd-httpx
RUN go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@v1.2.3
RUN go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@v2.5.0
RUN go install -v github.com/projectdiscovery/katana/cmd/katana@v1.5.0

# Install additional reconnaissance binaries via Go.
RUN go install github.com/tomnomnom/assetfinder@v0.1.1
RUN go install github.com/OJ/gobuster/v3@v3.8.2
RUN go install github.com/ffuf/ffuf/v2@v2.1.0

# Install the SecLists wordlist collection.
RUN git clone --depth 1 https://github.com/danielmiessler/SecLists.git /usr/share/wordlists/seclists && \
    rm -rf /usr/share/wordlists/seclists/.git

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
RUN pip install --upgrade sslyze==6.3.1

# Install rustscan from the official GitHub releases.
WORKDIR /tmp
RUN wget https://github.com/bee-san/RustScan/releases/download/2.4.1/x86_64-linux-rustscan.tar.gz.zip
RUN unzip x86_64-linux-rustscan.tar.gz.zip && \
    tar xzf x86_64-linux-rustscan.tar.gz && \
    mv rustscan /usr/local/bin/rustscan && \
    rm -rf x86_64-linux-rustscan*

# Install wpscan via RubyGems.
RUN gem install wpscan -v 3.8.28

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
