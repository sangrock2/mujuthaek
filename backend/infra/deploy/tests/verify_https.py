"""Isolated nginx TLS integration check. Requires Docker and OpenSSL; never uses deployment secrets."""

import http.client
import os
import shutil
import ssl
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True)


def main():
    deploy = Path(__file__).resolve().parents[1]
    artifacts = deploy / "build"
    artifacts.mkdir(exist_ok=True)
    openssl = os.environ.get("OPENSSL_BIN") or shutil.which("openssl")
    if not openssl:
        raise RuntimeError("OpenSSL is required")
    name = "mujuthaek-tls-check-" + uuid.uuid4().hex[:12]
    config = str(deploy / "nginx" / "default.conf")
    with tempfile.TemporaryDirectory(prefix="tls-", dir=artifacts) as directory:
        root = Path(directory)
        certs = root / "certs"
        certs.mkdir()
        run(
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-keyout",
            str(certs / "privkey.pem"),
            "-out",
            str(certs / "fullchain.pem"),
        )
        stub = root / "stub.conf"
        stub.write_text('server { listen 8080; location / { return 200 "upstream-ok"; } }', encoding="utf-8")
        webroot = root / "webroot"
        challenge = webroot / ".well-known/acme-challenge/test-token"
        challenge.parent.mkdir(parents=True)
        challenge.write_text("acme-test-only")
        base = [
            "docker",
            "run",
            "--add-host",
            "api:127.0.0.1",
            "--mount",
            f"type=bind,src={config},dst=/etc/nginx/conf.d/default.conf,readonly",
            "--mount",
            f"type=bind,src={deploy / 'nginx/acme.conf'},dst=/etc/nginx/conf.d/acme.conf,readonly",
            "--mount",
            f"type=bind,src={webroot},dst=/var/www/certbot,readonly",
        ]
        missing = run(*base, "--rm", "nginx:1.29-alpine", "nginx", "-t", check=False)
        assert missing.returncode != 0 and "fullchain.pem" in missing.stderr, missing.stderr
        mount = ["--mount", f"type=bind,src={certs},dst=/etc/nginx/tls,readonly"]
        run(*base, *mount, "--rm", "nginx:1.29-alpine", "nginx", "-t")
        try:
            run(
                *base,
                *mount,
                "--name",
                name,
                "-d",
                "-p",
                "127.0.0.1::443",
                "-p",
                "127.0.0.1::80",
                "--mount",
                f"type=bind,src={stub},dst=/etc/nginx/conf.d/stub.conf,readonly",
                "nginx:1.29-alpine",
            )
            port = int(run("docker", "port", name, "443/tcp").stdout.strip().rsplit(":", 1)[1])
            http_port = int(run("docker", "port", name, "80/tcp").stdout.strip().rsplit(":", 1)[1])
            trusted = ssl.create_default_context(cafile=str(certs / "fullchain.pem"))
            for attempt in range(50):
                try:
                    connection = http.client.HTTPSConnection("localhost", port, context=trusted, timeout=2)
                    connection.request("GET", "/api/auth/refresh")
                    response = connection.getresponse()
                    assert response.status == 200 and response.read() == b"upstream-ok"
                    connection.close()
                    break
                except OSError:
                    if attempt == 49:
                        raise
                    time.sleep(0.1)
            for host, context in [("localhost", ssl.create_default_context()), ("127.0.0.1", trusted)]:
                connection = http.client.HTTPSConnection(host, port, context=context, timeout=2)
                try:
                    connection.request("GET", "/api/auth/refresh")
                except ssl.SSLCertVerificationError:
                    pass
                else:
                    raise AssertionError("Untrusted or mismatched certificate was accepted")
                finally:
                    connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("GET", "/api/auth/refresh")
            response = connection.getresponse()
            assert response.status == 400 and b"upstream-ok" not in response.read()
            connection.close()
            for method, path, status, body in [
                ("GET", "/.well-known/acme-challenge/test-token", 200, b"acme-test-only"),
                ("GET", "/api/auth/refresh", 404, None),
                ("GET", "/oauth2/authorization/google", 404, None),
                ("POST", "/.well-known/acme-challenge/test-token", 403, None),
                ("GET", "/.well-known/acme-challenge/../other", 404, None),
            ]:
                connection = http.client.HTTPConnection("127.0.0.1", http_port, timeout=2)
                connection.request(method, path)
                response = connection.getresponse()
                data = response.read()
                assert response.status == status, (method, path, response.status)
                if body is not None:
                    assert data == body
                connection.close()
            print(
                "TLS/ACME checks passed: trusted HTTPS, trust/hostname enforcement, plaintext API rejection, ACME-only HTTP, missing-certificate failure"
            )
        finally:
            run("docker", "rm", "-f", name, check=False)


if __name__ == "__main__":
    main()
