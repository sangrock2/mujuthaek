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
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / 'backend/infra/deploy/personal/nginx/default.conf'
# The port-80 file the personal compose actually mounts (./nginx/acme.conf next to compose.prod.yml).
ACME = ROOT / 'backend/infra/deploy/personal/nginx/acme.conf'
# Path parameters and dot segments must never reach the application, raw or percent-encoded.
UNSAFE_PATHS = (
    '/api/..;/internal/config', '/api/..;/actuator/prometheus', '/api/v1/regions;jsessionid=1', '/api/%3B/internal',
    '/api/%3b/internal', '/api/%2e%2e/internal/config', '/api/%2E%2E/internal', '/api/.%2e/internal', '/api/%2e./internal',
    '/api/../internal/config', '/api/..', '/api/..?next=1', '/oauth2/..;/authorization/test', '/x/..;/api/test',
)
# Legitimate shapes, including semicolons and dots that appear only in the query string.
SAFE_PATHS = (
    '/api/test', '/api/v1/regions', '/actuator/health', '/oauth2/authorization/kakao',
    '/login/oauth2/code/google?code=abc&state=def', '/api/v1/notices?keyword=a;b', '/api/v1/notices?keyword=%3B%2e%2e',
    '/api/v1/notices?next=/../internal', '/api/v1/notices/0190f0e8-1234-7abc-8def-0123456789ab/files/1',
    '/api/v1/files/report.v2.pdf', '/api/v1/notices/a..b',
)
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


def server_names(config):
    """Names of the application server (not the catch-all `_` server); the first one is nginx's $server_name."""
    groups = [value.split() for value in re.findall(r'(?m)^\s*server_name\s+([^;]+);', config)]
    named = [group for group in groups if group != ['_']]
    if len(named) != 1:
        raise AssertionError('Expected exactly one named application server')
    return named[0]


def unsafe_uri_pattern(config):
    """The request-URI rule that rejects path parameters and dot segments before any location is chosen."""
    found = re.findall(r'(?m)^ {4}if \(\$request_uri ~\* "([^"]+)"\) \{ return 400; \}$', config)
    if len(found) != 1:
        raise AssertionError('Unsafe request-URI rule not found at server level')
    return re.compile(found[0], re.IGNORECASE)


def static_checks(config):
    """Configuration properties that need no Docker; the CI evidence and the local unit tests both use them."""
    results = {}
    gaps = limit_gaps(config)
    assert not gaps, f'Proxied locations without per-address and server-wide limits: {gaps}'
    results['every_proxied_location_has_ip_and_total_limits'] = True
    pattern = unsafe_uri_pattern(config)
    missed = [path for path in UNSAFE_PATHS if not pattern.search(path)]
    blocked = [path for path in SAFE_PATHS if pattern.search(path)]
    assert not missed and not blocked, f'Unsafe-path rule misses {missed} or blocks legitimate {blocked}'
    results['unsafe_path_rule_blocks_only_path_segments'] = True
    blocks = re.split(r'(?m)^server \{$', config)[1:]
    assert len(blocks) == 2, 'Expected a catch-all server and one named application server'
    catch_all = [block for block in blocks if re.search(r'(?m)^\s*server_name _;$', block)]
    assert len(catch_all) == 1 and 'listen 443 ssl default_server;' in catch_all[0], 'Catch-all must be the default'
    assert re.search(r'(?m)^\s*return 444;$', catch_all[0]) and 'proxy_pass' not in catch_all[0]
    for block in blocks:
        assert re.search(r'(?m)^\s*ssl_session_tickets off;$', block), 'TLS session tickets must be off on every server'
    application = blocks[1 - blocks.index(catch_all[0])]
    assert 'add_header Strict-Transport-Security "max-age=31536000" always;' in application
    assert len(re.findall(r'Strict-Transport-Security', config)) == 1, 'One HSTS policy, never preload'
    assert re.search(r'(?m)^\s*proxy_set_header X-Forwarded-Host \$server_name;$', application)
    assert not re.search(r'(?m)^\s*proxy_set_header X-Forwarded-Host \$(host|http_host)\b', config)
    results['tls_and_forwarded_host_pinned'] = True
    return results


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
        self.names = server_names(config)
        self.host = self.names[0]
        if config.count('listen 443 ssl') != 2:
            raise AssertionError('Expected the catch-all and the application server on 443')
        config = config.replace('listen 443 ssl', f'listen 127.0.0.1:{self.port} ssl')
        config = config.replace('http://api:8080', f'http://127.0.0.1:{upstream}')
        (directory / 'default.conf').write_text(config, encoding='utf-8')
        acme = ACME.read_text(encoding='utf-8')
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

    def exchange(self, path, headers=None, source=None):
        # Requests name the configured API host unless a check overrides Host; unknown hosts are dropped (444).
        with closing(self.connection(source)) as client:
            client.request('GET', path, headers={'Host': self.host, **(headers or {})})
            response = client.getresponse()
            return response.status, {key.lower(): value for key, value in response.getheaders()}, response.read()

    def get(self, path, headers=None, source=None):
        status, _, body = self.exchange(path, headers, source)
        return status, body

    def dropped(self, path, host):
        """True when nginx closes the connection without sending any HTTP response."""
        try:
            self.get(path, {'Host': host})
        except TimeoutError:
            raise
        except (http.client.HTTPException, OSError):
            return True
        return False

    def close(self):
        command('docker', 'rm', '-f', self.name)


def main():
    results = static_checks(CONFIG.read_text(encoding='utf-8'))
    if '--static-only' in sys.argv[1:]:
        # Docker-free subset for local runs. CI runs the full harness and counts every check.
        print(json.dumps({'ok': True, 'static_only': True, 'checks': results}, indent=2))
        return
    upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='gateway-security-') as temporary:
        directory = Path(temporary)
        command('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=localhost', '-keyout', str(directory / 'privkey.pem'), '-out', str(directory / 'fullchain.pem'))
        gateway = Gateway(directory, upstream.server_port)
        try:
            marker = 'synthetic-query-canary-' + uuid.uuid4().hex
            # The alias (the fixed IP) reaches the application, but the app always sees the configured primary name.
            status, response_headers, body = gateway.exchange('/api/test?code=' + marker, {
                'Host': gateway.names[-1],
                'X-Forwarded-For': '203.0.113.19', 'Forwarded': 'for=203.0.113.19;proto=http',
                'X-Forwarded-Prefix': '/actuator', 'X-Forwarded-Host': 'evil.example',
            })
            assert status == 200
            headers = {key.lower(): value for key, value in json.loads(body).items()}
            assert headers['x-forwarded-for'] == '127.0.0.1'
            assert headers['x-forwarded-proto'] == 'https'
            assert headers['x-forwarded-host'] == gateway.host
            assert 'forwarded' not in headers and 'x-forwarded-prefix' not in headers
            results['forwarded_headers_cannot_spoof_identity'] = True
            assert response_headers.get('strict-transport-security') == 'max-age=31536000'
            rejected = gateway.exchange('/api/..;/internal/config')
            assert rejected[0] == 400 and rejected[1].get('strict-transport-security') == 'max-age=31536000'
            results['hsts_sent_on_https_responses'] = True
            before = len(SEEN)
            for host in ('evil.example', '127.0.0.1', gateway.host + '.evil.example'):
                assert gateway.dropped('/api/test', host), host
            assert len(SEEN) == before
            results['unknown_host_dropped_without_upstream'] = True
            for path in ('/internal', '/internal/config', '/actuator/env'):
                before = len(SEEN)
                assert gateway.get(path)[0] == 404
                assert len(SEEN) == before
            results['internal_and_management_paths_blocked'] = True
            before = len(SEEN)
            for path in UNSAFE_PATHS:
                assert gateway.get(path)[0] == 400, path
            assert len(SEEN) == before
            # Semicolons in the query string are ordinary search input and still reach the application unchanged.
            assert gateway.get('/api/v1/notices?keyword=a;b%3B')[0] == 200
            assert SEEN[-1] == '/api/v1/notices?keyword=a;b%3B'
            results['unsafe_path_segments_rejected_before_upstream'] = True
            with closing(http.client.HTTPConnection('127.0.0.1', gateway.http_port, timeout=5)) as client:
                client.request('GET', '/api/test?token=' + marker)
                assert client.getresponse().status == 404
            results['plaintext_listener_never_proxies_application'] = True
            # Send just the headers: oversized declared body must be rejected before it reaches the app.
            before = len(SEEN)
            with closing(gateway.connection()) as client:
                client.putrequest('POST', '/api/test?token=' + marker, skip_host=True)
                client.putheader('Host', gateway.host)
                client.putheader('Content-Length', str(1024 * 1024 + 1))
                client.endheaders()
                assert client.getresponse().status == 413
            assert len(SEEN) == before
            results['oversized_body_blocked_before_upstream'] = True
            with closing(gateway.connection()) as client:
                client.putrequest('POST', '/api/test', skip_host=True)
                client.putheader('Host', gateway.host)
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
                client.request('GET', path, headers={'Host': gateway.host})
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
