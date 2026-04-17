import sqlite3
import uuid
import datetime

SESSION_ID = "1dc84894-69f1-4606-b69b-c959b130ae05"
DB = "data/history.db"

commands = [
    ("nmap -sV darklab.sh",           0, "Starting Nmap 7.94\nNmap scan report for darklab.sh"),
    ("dig darklab.sh A",              0, "; <<>> DiG 9.18 <<>> darklab.sh A\n;; ANSWER SECTION:"),
    ("ping -c 4 8.8.8.8",             0, "PING 8.8.8.8: 56 bytes\n64 bytes from 8.8.8.8: icmp_seq=0"),
    ("curl -I https://darklab.sh",    0, "HTTP/2 200\ncontent-type: text/html"),
    ("openssl s_client -connect darklab.sh:443 -brief", 0, "CONNECTION ESTABLISHED\nProtocol version: TLSv1.3"),
    ("whois darklab.sh",              0, "Domain Name: DARKLAB.SH\nRegistrar: Njalla"),
    ("traceroute darklab.sh",         0, "traceroute to darklab.sh, 30 hops max\n 1  192.168.1.1  1.2 ms"),
    ("nmap -p 80,443 darklab.sh",     0, "PORT    STATE SERVICE\n80/tcp  open  http\n443/tcp open  https"),
    ("curl -s https://darklab.sh/health", 0, '{"status":"ok"}'),
    ("host darklab.sh",               0, "darklab.sh has address 1.2.3.4"),
]

conn = sqlite3.connect(DB)
now = datetime.datetime.now(datetime.timezone.utc)
for i, (cmd, code, output) in enumerate(commands):
    started = (now - datetime.timedelta(minutes=len(commands) - i)).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO runs"
        " (id, session_id, command, started, finished, exit_code, output, output_preview)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), SESSION_ID, cmd, started, started, code, output, output[:200])
    )
conn.commit()
conn.close()
print(f"Inserted {len(commands)} fake runs for session {SESSION_ID[:20]}...")
