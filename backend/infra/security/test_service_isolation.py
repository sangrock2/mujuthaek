"""Real RabbitMQ denial checks against a disposable loopback-only broker, using synthetic credentials."""
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path

import pika

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend/infra/deploy/personal'))
import service_isolation as isolation


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Disposable Docker operation failed: ' + (result.stderr or result.stdout)[-1400:])
    return result.stdout.strip()


def main():
    passwords = {service: secrets.token_hex(32) for service in isolation.SERVICES}
    directory = ROOT / 'backend/infra/security/build'
    directory.mkdir(exist_ok=True)
    path = directory / ('mq-isolation-synthetic-' + secrets.token_hex(6) + '.json')
    path.write_text(json.dumps(isolation.topology(passwords)), encoding='utf-8')
    container = None
    results = {}
    try:
        image = 'rabbitmq:4.1@sha256:16bf771308e2b6ff8ea4ed8fa202a82ccbfa29e0f140835f7564603762073593'
        config = ROOT / 'backend/infra/deploy/personal/rabbitmq/isolation.conf'
        container = docker('run', '-d', '--rm', '--user', 'rabbitmq', '--memory', '512m', '--cpus', '1',
                           '--security-opt', 'no-new-privileges:true', '-p', '127.0.0.1::5672',
                           '-e', 'RABBITMQ_DEFAULT_USER=mujuthaek', '-e', 'RABBITMQ_DEFAULT_PASS=synthetic-unused',
                           '--mount', f'type=bind,src={config},dst=/etc/rabbitmq/conf.d/90-isolation.conf,readonly',
                           '--mount', f'type=bind,src={path},dst=/etc/rabbitmq/definitions.json,readonly', image)
        for attempt in range(60):
            ready = subprocess.run(['docker', 'exec', container, 'rabbitmq-diagnostics', '-q', 'check_running'], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Disposable broker did not start')
        users = json.loads(docker('exec', container, 'rabbitmqctl', 'list_users', '--formatter=json'))
        results['fresh_boot.only_service_users'] = sorted(item['user'] for item in users) == sorted(isolation.USERS.values())
        if not results['fresh_boot.only_service_users']:
            raise RuntimeError('Fresh broker created an unexpected default user')
        port = int(docker('port', container, '5672/tcp').rsplit(':', 1)[1])

        def connect(service):
            return pika.BlockingConnection(pika.ConnectionParameters('127.0.0.1', port,
                credentials=pika.PlainCredentials(isolation.USERS[service], passwords[service]), socket_timeout=5))

        for service in isolation.SERVICES:
            connection = connect(service)
            try:
                channel = connection.channel()
                channel.confirm_delivery()
                channel.exchange_declare(exchange=isolation.EVENTS, passive=True)
                channel.basic_publish(isolation.EVENTS, isolation.PUBLISH[service][0], b'{"synthetic":true}', mandatory=False)
                results[service + '.own_publish'] = True
                owned = [name for name, spec in isolation.QUEUES.items() if spec[0] == service]
                for queue in owned:
                    channel.queue_declare(queue=queue, passive=True)
                    channel.basic_get(queue=queue, auto_ack=True)
                results[service + '.owned_reads'] = True
                for key, exchange, routing in (
                    ('default_exchange_denied', '', 'mujuthaek.notification'),
                    ('foreign_topic_denied', isolation.EVENTS,
                     'notification.requested' if service != 'api' else 'raw.notice.collected'),
                ):
                    channel = connection.channel()
                    channel.confirm_delivery()
                    try:
                        channel.basic_publish(exchange, routing, b'{"synthetic":true}')
                        raise AssertionError(service + ': unauthorized publication accepted')
                    except pika.exceptions.ChannelClosedByBroker as error:
                        assert error.reply_code == 403
                        results[service + '.' + key] = True
                for key, action in (
                    ('queue_creation_denied', lambda c: c.queue_declare(queue='unauthorized.synthetic.queue')),
                    ('foreign_read_denied', lambda c: c.basic_get(
                        queue='mujuthaek.raw.collected' if service != 'extraction' else 'mujuthaek.notification')),
                ):
                    channel = connection.channel()
                    try:
                        action(channel)
                        raise AssertionError(service + ': unauthorized queue operation accepted')
                    except pika.exceptions.ChannelClosedByBroker as error:
                        assert error.reply_code == 403
                        results[service + '.' + key] = True
            finally:
                connection.close()
        print(json.dumps({'ok': True, 'checks': results, 'production_calls': 0}, indent=2))
    finally:
        path.unlink(missing_ok=True)
        if container:
            docker('rm', '-f', container)


if __name__ == '__main__':
    main()
