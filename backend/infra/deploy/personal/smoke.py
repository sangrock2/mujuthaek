"""Read-only HTTPS smoke checks against the deployed personal service; TLS verification stays enabled."""
import argparse
import http.client
import ipaddress
import json
import re
import socket
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def request(origin, path, connect_to=None):
    if connect_to:
        parsed = urlsplit(origin)
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, context=ssl.create_default_context(), timeout=30)
        # Connect to the staging IP while validating the certificate for the unchanged public origin.
        connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection((connect_to, address[1]), timeout, source_address)
        try:
            connection.request("GET", path, headers={"Host": parsed.netloc})
            response = connection.getresponse()
            return response.status, response.read(512 * 1024), response.headers
        finally:
            connection.close()
    try:
        with urllib.request.urlopen(origin + path, timeout=30) as response:
            return response.status, response.read(512 * 1024), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read(4096), error.headers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin")
    parser.add_argument("--connect-to", help="Staging server IP; certificate verification still uses the public origin")
    args = parser.parse_args()
    if args.connect_to and not ipaddress.ip_address(args.connect_to).is_global:
        parser.error("Staging target must be a public IP")
    origin = args.origin.rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        parser.error("Use a bare HTTPS origin")
    checks = [("/", 200), ("/login", 200), ("/me/preparations", 200),
              ("/actuator/health", 200), ("/api/v1/regions", 200),
              ("/api/users/me", 401), ("/api/users/me/preparations", 401),
              ("/actuator/env", 404), ("/internal/stats", 404)]
    root = None
    for path, expected in checks:
        status, body, headers = request(origin, path, args.connect_to)
        if status != expected:
            raise AssertionError(f"{path}: expected {expected}, got {status}")
        if path == "/":
            root = body.decode("utf-8")
            if "<html" not in root or headers.get("X-Content-Type-Options") != "nosniff":
                raise AssertionError("Frontend HTML/security header missing")
        if path == "/actuator/health" and json.loads(body).get("status") != "UP":
            raise AssertionError("API health is not UP")
        print(json.dumps({"path": path, "status": status}))
    asset = re.search(r'src="(/_next/static/[^"<>]+\.js)"', root)
    if not asset or request(origin, asset.group(1), args.connect_to)[0] != 200:
        raise AssertionError("Frontend JavaScript asset was not served")
    print("HTTPS, frontend asset, public API, unauthenticated access and private paths verified")


if __name__ == "__main__":
    main()
