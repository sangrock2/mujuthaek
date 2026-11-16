"""Bounded adversarial checks against the real nginx configuration, on loopback only.

No production URL or credential is accepted. Docker and openssl are required.
"""
import concurrent.futures
from contextlib import closing
import http.client
import http.server
import json
import re
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / 'backend/infra/deploy/personal/nginx/default.conf'
CONTEXT = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
CONTEXT.check_hostname = False  # only the locally generated test certificate
CONTEXT.verify_mode = ssl.CERT_NONE
STOP = threading.Event()
SEEN = []


class Upstream(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass

    def do_GET(self):
        SEEN.append(self.path)
        if self.path.endswith('/chat/stream'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            self.wfile.write(b': connected\n\n')
            self.wfile.flush()
            STOP.wait(30)
            self.close_connection = True
            return
        data = json.dumps(dict(self.headers)).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=120).stdout


def locations(config):
    """Every location block with its own directives. Quoted strings, comments and one-line blocks are handled."""
    found, stack, words = [], [], []
    for token in re.findall(r"'[^']*'|\"[^\"]*\"|#[^\n]*|[{};]|[^\s{};'\"#]+", config):
        if token.startswith('#'):
            continue
        if token == '{':
            stack.append((words, []))
            words = []
        elif token == '}':
            name, directives = stack.pop()
            if name[:1] == ['location']:
                found.append((' '.join(name[1:]), directives))
            words = []
        elif token == ';':
            if stack:
                stack[-1][1].append(words)
            words = []
        else:
            words.append(token)
    return found


def limit_gaps(config):
    """Proxied locations without both a per-address and a server-wide request limit.

    Each location is checked on its own directives: nginx ignores the parent's limit_req once a location declares any.
    """
    zones = {zone: key for key, zone in re.findall(r'(?m)^\s*limit_req_zone\s+(\S+)\s+zone=([\w-]+):', config)}
    proxied = [(name, directives) for name, directives in locations(config)
               if any(directive[:1] == ['proxy_pass'] for directive in directives)]
    if not proxied:
        raise AssertionError('No proxied locations found; the gateway configuration was not parsed')
    gaps = []
    for name, directives in proxied:
        keys = {zones.get(word.split('=', 1)[1]) for directive in directives if directive[:1] == ['limit_req']
                for word in directive[1:] if word.startswith('zone=')}
        if not {'$binary_remote_addr', '$server_name'} <= keys:
            gaps.append(name)
    return gaps


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Gateway:
    def __init__(self, directory, upstream):
        self.name = 'mujuthaek-security-test-' + uuid.uuid4().hex
        self.port = free_port()
        self.http_port = free_port()
        while self.http_port == self.port:
            self.http_port = free_port()
        config = CONFIG.read_text(encoding='utf-8')
        config = config.replace('listen 443 ssl default_server;', f'listen 127.0.0.1:{self.port} ssl default_server;')
        config = config.replace('http://api:8080', f'http://127.0.0.1:{upstream}')
        (directory / 'default.conf').write_text(config, encoding='utf-8')
        acme = (ROOT / 'backend/infra/deploy/nginx/acme.conf').read_text(encoding='utf-8')
        (directory / 'acme.conf').write_text(acme.replace('listen 80 default_server;', f'listen 127.0.0.1:{self.http_port} default_server;'), encoding='utf-8')
        command('docker', 'run', '-d', '--name', self.name, '--network', 'host',
                '--mount', f'type=bind,src={directory / "default.conf"},dst=/etc/nginx/conf.d/default.conf,readonly',
                '--mount', f'type=bind,src={directory / "acme.conf"},dst=/etc/nginx/conf.d/acme.conf,readonly',
                '--mount', f'type=bind,src={directory},dst=/etc/nginx/tls,readonly',
                '--entrypoint', 'nginx', 'nginx:1.29-alpine', '-g', 'daemon off;')
        try:
            command('docker', 'exec', self.name, 'nginx', '-t')
            for _ in range(50):
                try:
                    if self.get('/actuator/health')[0] == 200:
                        return
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(.1)
            raise AssertionError('Local nginx did not become ready')
        except BaseException:
            self.close()
            raise

    def connection(self, source=None):
        # Any 127.0.0.0/8 source address works on Linux loopback, so one host can act as many clients.
        return http.client.HTTPSConnection('127.0.0.1', self.port, context=CONTEXT, timeout=5,
                                           source_address=(source, 0) if source else None)

    def get(self, path, headers=None, source=None):
        with closing(self.connection(source)) as client:
            client.request('GET', path, headers=headers or {})
            response = client.getresponse()
            return response.status, response.read()

    def close(self):
        command('docker', 'rm', '-f', self.name)


def main():
    results = {}
    gaps = limit_gaps(CONFIG.read_text(encoding='utf-8'))
    assert not gaps, f'Proxied locations without per-address and server-wide limits: {gaps}'
    results['every_proxied_location_has_ip_and_total_limits'] = True
    upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='gateway-security-') as temporary:
        directory = Path(temporary)
        command('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=localhost', '-keyout', str(directory / 'privkey.pem'), '-out', str(directory / 'fullchain.pem'))
        gateway = Gateway(directory, upstream.server_port)
        try:
            marker = 'synthetic-query-canary-' + uuid.uuid4().hex
            status, body = gateway.get('/api/test?code=' + marker, {
                'X-Forwarded-For': '203.0.113.19', 'Forwarded': 'for=203.0.113.19;proto=http',
                'X-Forwarded-Prefix': '/actuator', 'X-Forwarded-Host': 'evil.example',
            })
            assert status == 200
            headers = {key.lower(): value for key, value in json.loads(body).items()}
            assert headers['x-forwarded-for'] == '127.0.0.1'
            assert headers['x-forwarded-proto'] == 'https'
            assert headers['x-forwarded-host'] == '127.0.0.1'
            assert 'forwarded' not in headers and 'x-forwarded-prefix' not in headers
            results['forwarded_headers_cannot_spoof_identity'] = True
            for path in ('/internal', '/internal/config', '/actuator/env', '/api/../internal/config'):
                before = len(SEEN)
                assert gateway.get(path)[0] == 404
                assert len(SEEN) == before
            results['internal_and_management_paths_blocked'] = True
            with closing(http.client.HTTPConnection('127.0.0.1', gateway.http_port, timeout=5)) as client:
                client.request('GET', '/api/test?token=' + marker)
                assert client.getresponse().status == 404
            results['plaintext_listener_never_proxies_application'] = True
            # Send just the headers: oversized declared body must be rejected before it reaches the app.
            before = len(SEEN)
            with closing(gateway.connection()) as client:
                client.putrequest('POST', '/api/test?token=' + marker)
                client.putheader('Content-Length', str(1024 * 1024 + 1))
                client.endheaders()
                assert client.getresponse().status == 413
            assert len(SEEN) == before
            results['oversized_body_blocked_before_upstream'] = True
            with closing(gateway.connection()) as client:
                client.putrequest('POST', '/api/test')
                client.putheader('Content-Length', '1')
                client.putheader('Transfer-Encoding', 'chunked')
                client.endheaders(b'0\r\n\r\n')
                assert client.getresponse().status == 400
            results['ambiguous_request_framing_rejected'] = True
            oauth = [gateway.get('/oauth2/authorization/test', {'X-Forwarded-For': f'203.0.113.{n}'})[0] for n in range(9)]
            assert 200 in oauth and 429 in oauth
            results['oauth_limit_not_bypassed_by_forged_ip'] = True
            downloads = [gateway.get('/api/v1/notices/test/files/pdf')[0] for _ in range(10)]
            assert 200 in downloads and 429 in downloads
            results['download_rate_separately_bounded'] = True
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                statuses = list(pool.map(lambda n: gateway.get('/api/test', {'X-Forwarded-For': f'203.0.113.{n}'})[0], range(96)))
            assert 200 in statuses and 429 in statuses
            results['api_burst_bounded_despite_forged_ip'] = True
            time.sleep(.2)
            logs = subprocess.run(['docker', 'logs', gateway.name], capture_output=True, text=True, check=True, timeout=30)
            assert marker not in logs.stdout + logs.stderr
            results['query_secrets_excluded_from_gateway_logs'] = True
        finally:
            gateway.close()
        gateway = Gateway(directory, upstream.server_port)
        clients, responses = [], []
        try:
            path = '/api/v1/notices/' + str(uuid.uuid4()) + '/chat/stream'
            for _ in range(48):
                client = gateway.connection()
                clients.append(client)
                client.request('GET', path)
                response = client.getresponse()
                responses.append(response)
                assert response.status == 200
            assert gateway.get(path)[0] == 429
            # SSE saturation must not consume the entire ordinary API budget.
            assert gateway.get('/api/test')[0] == 200
            results['sse_capacity_reserved_without_blocking_normal_api'] = True
        finally:
            for response in responses:
                response.close()
            for client in clients:
                client.close()
            STOP.set()
            gateway.close()
        # Fresh limit zones so earlier bursts cannot decide these results.
        gateway = Gateway(directory, upstream.server_port)
        try:
            # Each health call checks the database and the broker; only admitted calls may reach the upstream.
            before = len(SEEN)
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                statuses = list(pool.map(lambda _: gateway.get('/actuator/health')[0], range(96)))
            assert 200 in statuses and 429 in statuses
            assert len(SEEN) - before == statuses.count(200)
            results['health_check_rate_limited_before_upstream'] = True
            # One request per source address never trips the per-address zone, so any 429 is the server-wide budget.
            statuses = [gateway.get('/oauth2/authorization/test', source=f'127.0.0.{n}')[0] for n in range(10, 50)]
            assert 200 in statuses and 429 in statuses
            results['oauth_start_limited_across_client_addresses'] = True
        finally:
            gateway.close()
    upstream.shutdown()
    print(json.dumps({'ok': True, 'checks': results}, indent=2))


if __name__ == '__main__':
    main()
