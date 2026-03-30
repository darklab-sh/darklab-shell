FROM python:3.12-slim

RUN apt-get update
RUN apt-get install -y procps net-tools curl wget iputils-ping nmap dnsutils traceroute mtr whois tcptraceroute testssl.sh dnsrecon git libnet-ssleay-perl libxml-writer-perl libjson-perl

WORKDIR /opt/
RUN git clone https://github.com/sullo/Nikto.git
RUN chmod -R 755 *
RUN ln -s /opt/Nikto/program/nikto.pl /usr/local/bin/nikto

WORKDIR /app
RUN pip install wapiti3
RUN pip install --no-cache-dir flask

EXPOSE 8888

CMD ["python3", "app.py"]
