FROM python:3.12-slim

# Ensure all packages are up to date and install dependencies and tools
RUN apt-get update
RUN apt-get upgrade -y

RUN apt-get install -y  procps net-tools curl wget iputils-ping nmap dnsutils traceroute \
                        mtr whois tcptraceroute testssl.sh dnsrecon git libnet-ssleay-perl build-essential \
                        libxml-writer-perl libjson-perl golang-go rubygems ruby-dev

# Install nuclei via Go and create symlink
RUN go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
RUN ln -s /root/go/bin/nuclei /usr/local/bin/nuclei

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

EXPOSE 8888

CMD ["gunicorn", "--bind", "0.0.0.0:8888", "--workers", "1", "--threads", "8", "--timeout", "3600", "--control-socket", "/tmp/.gunicorn", "app:app"]