FROM python:3.12-slim

WORKDIR /app

RUN apt-get update
RUN apt-get install -y procps net-tools curl wget iputils-ping nmap dnsutils traceroute
RUN pip install --no-cache-dir flask

EXPOSE 8888

CMD ["python3", "app.py"]
