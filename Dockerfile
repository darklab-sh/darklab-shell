FROM python:3.12-slim

# Ensure all packages are up to date and install dependencies and tools
RUN apt-get update
RUN apt-get upgrade -y

RUN apt-get install -y  procps net-tools curl wget iputils-ping nmap dnsutils traceroute \
                        mtr whois tcptraceroute testssl.sh dnsrecon git libnet-ssleay-perl \
                        libxml-writer-perl libjson-perl golang-go rubygems ruby-dev build-essential

# Set GOBIN so all Go binaries install directly into /usr/local/bin,
# world-executable and not owned by root's home directory
ENV GOBIN=/usr/local/bin

# Install nuclei
RUN go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest

# Install ProjectDiscovery suite via Go
# Note: httpx binary is renamed to pd-httpx to avoid collision with the Python
# httpx library (pulled in by wapiti3) which would otherwise shadow the Go binary
RUN go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    mv /usr/local/bin/httpx /usr/local/bin/pd-httpx
RUN go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest

# Install gobuster
RUN go install github.com/OJ/gobuster/v3@latest

# Install wordlists for gobuster (selective clone — web content and DNS only, ~50MB vs 1.8GB for full SecLists)
RUN mkdir -p /usr/share/wordlists && \
    git clone --depth 1 --filter=blob:none --sparse https://github.com/danielmiessler/SecLists.git /tmp/seclists && \
    cd /tmp/seclists && \
    git sparse-checkout set Discovery/Web-Content Discovery/DNS && \
    cp -r Discovery /usr/share/wordlists/seclists && \
    rm -rf /tmp/seclists

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

# Install wapiti3 via pip
RUN pip install wapiti3

# Install wpscan via ruby gems
RUN gem install wpscan

# Install required Python dependencies from requirements.txt
WORKDIR /app

COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create two unprivileged users:
#   appuser — owns /data and runs Gunicorn (can write SQLite database)
#   scanner — runs all user-submitted commands, no write access to /data
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    groupadd -r scanner && useradd -r -g scanner -s /usr/sbin/nologin scanner

# Grant nmap raw socket capabilities so the scanner user can use OS
# fingerprinting and other features that require elevated network access,
# without giving the scanner user full root privileges.
RUN apt-get install -y libcap2-bin sudo gosu && \
    setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap && \
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