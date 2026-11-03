# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exercise SSLyze certificate parsing against a disposable local TLS server."""

from datetime import datetime, timedelta, timezone
import ipaddress
import json
from pathlib import Path
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        now = datetime.now(timezone.utc)
        certificate = (
            x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256())
        )
        (root / "cert.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        (root / "key.pem").write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / "cert.pem", root / "key.pem")

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(2)
                try:
                    with context.wrap_socket(self.request, server_side=True) as connection:
                        connection.recv(1)
                except (OSError, ssl.SSLError):
                    pass  # Scanner probes close connections without an application request.

        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as server:
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                report = root / "scan.json"
                subprocess.run([
                    sys.executable, "-m", "sslyze", "--certinfo", "--quiet",
                    f"--json_out={report}", f"127.0.0.1:{server.server_address[1]}",
                ], check=True, capture_output=True, text=True, timeout=30)
                result = json.loads(report.read_text())["server_scan_results"][0]
                assert result["scan_status"] == "COMPLETED", result
                certinfo = result["scan_result"]["certificate_info"]
                assert certinfo["status"] == "COMPLETED", certinfo
                assert certinfo["result"]["certificate_deployments"], certinfo
                print("SSLyze certificate scan completed with the patched cryptography dependency")
            finally:
                server.shutdown()
                thread.join(timeout=5)


if __name__ == "__main__":
    main()
