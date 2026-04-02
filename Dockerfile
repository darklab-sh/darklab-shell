FROM python:3.12-slim

# Ensure all packages are up to date and install dependencies and tools
RUN apt-get update
RUN apt-get upgrade -y

RUN apt-get install -y  procps net-tools curl wget iputils-ping nmap dnsutils traceroute netcat-traditional \
                        mtr whois tcptraceroute testssl.sh dnsrecon git libnet-ssleay-perl golang-go \
                        libxml-writer-perl libjson-perl rubygems ruby-dev build-essential fping hping3 \
                        masscan python3-requests fierce dnsenum libcap2-bin sudo gosu

# Set GOBIN so all Go binaries install directly into /usr/local/bin,
# world-executable and not owned by root's home directory
ENV GOBIN=/usr/local/bin

# Install nuclei
RUN go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@v3.7.1

# Install ProjectDiscovery suite via Go
# Note: httpx binary is renamed to pd-httpx to avoid collision with the Python
# httpx library (pulled in by wapiti3) which would otherwise shadow the Go binary
RUN go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@v2.13.0
RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@v1.9.0 && \
    mv /usr/local/bin/httpx /usr/local/bin/pd-httpx
RUN go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@v1.2.3

# Install amass, assetfinder, gobuster and ffuf via Go
RUN CGO_ENABLED=0 go install -v github.com/owasp-amass/amass/v5/cmd/amass@v5.0.1
RUN go install github.com/tomnomnom/assetfinder@v0.1.1
RUN go install github.com/OJ/gobuster/v3@v3.8.2
RUN go install github.com/ffuf/ffuf/v2@v2.1.0

# Install the full SecLists wordlist collection
RUN git clone --depth 1 https://github.com/danielmiessler/SecLists.git /usr/share/wordlists/seclists && \
    rm -rf /usr/share/wordlists/seclists/.git

# Point nuclei at /tmp so it works with read_only: true (tmpfs is mounted there)
ENV NUCLEI_TEMPLATES_DIR=/tmp/nuclei-templates
ENV HOME=/tmp

# Install nikto via git and create symlink
WORKDIR /opt/
RUN git clone https://github.com/sullo/Nikto.git
RUN chmod -R 755 *
RUN ln -s /opt/Nikto/program/nikto.pl /usr/local/bin/nikto

# Upgrade pip to ensure latest versions of dependencies can be installed
RUN pip install --upgrade pip

# Install wapiti3, dirsearch, and wafw00f via pip
RUN pip install wapiti3==3.2.2
RUN pip install wafw00f==2.4.2

# Install wpscan via ruby gems
RUN gem install wpscan -v 3.8.28

# Install required Python dependencies from requirements.txt
WORKDIR /app

COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Download the latest ansi_up at build time, overwriting the bundled fallback.
# The || true ensures a build failure here doesn't abort the image build —
# the committed copy in the repo is used by docker-compose via the bind mount.
RUN mkdir -p /app/static/js/vendor && \
    curl -sSL https://cdn.jsdelivr.net/npm/ansi_up/ansi_up.js \
         -o /app/static/js/vendor/ansi_up.js || true

# Create two unprivileged users:
#   appuser — owns /data and runs Gunicorn (can write SQLite database)
#   scanner — runs all user-submitted commands, no write access to /data
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    groupadd -r scanner && useradd -r -g scanner -s /usr/sbin/nologin scanner

# Grant nmap raw socket capabilities so the scanner user can use OS
# fingerprinting and other features that require elevated network access,
# without giving the scanner user full root privileges.

RUN setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap && \
    echo "appuser ALL=(scanner) NOPASSWD: ALL" >> /etc/sudoers

# Pre-create /data owned by appuser with 700 permissions.
# scanner user cannot write here. The entrypoint re-applies ownership
# after the Docker volume mount potentially resets it.
RUN mkdir -p /data && chown appuser:appuser /data && chmod 700 /data

# Copy entrypoint script — runs as root to fix /data ownership after volume
# mount, then drops to appuser via gosu before starting Gunicorn
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8888

ENTRYPOINT ["/entrypoint.sh"]