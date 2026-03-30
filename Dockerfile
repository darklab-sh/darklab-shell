FROM python:3.12-slim

WORKDIR /app

RUN apt-get update
RUN apt-get install -y procps net-tools curl wget iputils-ping nmap dnsutils traceroute mtr whois tcptraceroute testssl.sh dnsrecon git libnet-ssleay-perl libxml-writer-perl libjson-perl golang-go

# Install nuclei
RUN go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
RUN ln -s /root/go/bin/nuclei /usr/local/bin/nuclei

WORKDIR /opt/
RUN git clone https://github.com/sullo/Nikto.git
RUN chmod -R 755 *
RUN ln -s /opt/Nikto/program/nikto.pl /usr/local/bin/nikto

WORKDIR /app

# Point nuclei at /tmp so it works with read_only: true (tmpfs is mounted there)
ENV NUCLEI_TEMPLATES_DIR=/tmp/nuclei-templates
ENV HOME=/tmp

RUN pip install wapiti3

COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

EXPOSE 8888

CMD ["gunicorn", "--bind", "0.0.0.0:8888", "--workers", "1", "--threads", "8", "--timeout", "3600", "--control-socket", "/tmp/.gunicorn", "app:app"]
