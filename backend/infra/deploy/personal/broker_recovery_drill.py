"""Measure recovery on two disposable, loopback-only RabbitMQ containers."""

import argparse
import json
import sqlite3
import subprocess
import time
import uuid

import pika
import service_isolation as isolation
from mujuthaek_platform import recovery

QUEUE = recovery.RESULT_QUEUE
DLQ = QUEUE + '.dlq'
BINDING = {'queue': QUEUE, 'exchange': recovery.RETRY_EXCHANGE, 'routing_key': QUEUE}


def measure(docker, image, count):
    prefix = 'mujuthaek-local-recovery-' + uuid.uuid4().hex[:12]
    admin_password, operator_password = uuid.uuid4().hex, uuid.uuid4().hex
    containers = []
    result = {'events': count}

    def command(*args, data=None):
        return subprocess.run([*docker, *args], input=data, capture_output=True, check=True, timeout=45).stdout

    def create(suffix):
        name = prefix + suffix
        command('run', '--rm', '-d', '--name', name, '--label', 'mujuthaek.scope=local-rto',
                '-p', '127.0.0.1::5672', '-e', 'RABBITMQ_DEFAULT_USER=drill',
                '-e', 'RABBITMQ_DEFAULT_PASS=' + admin_password, image)
        containers.append(name)
        port = int(command('port', name, '5672/tcp').decode().strip().removeprefix('127.0.0.1:'))
        return name, port

    def connect(port, user='drill', password=admin_password):
        params = pika.ConnectionParameters('127.0.0.1', port, '/', pika.PlainCredentials(user, password),
                                           socket_timeout=1, stack_timeout=2)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                return pika.BlockingConnection(params)
            except pika.exceptions.AMQPConnectionError:
                time.sleep(0.2)
        raise RuntimeError('Local RabbitMQ readiness timeout')

    def restore(name):
        definitions = isolation.topology({name: uuid.uuid4().hex for name in isolation.SERVICES})
        for section, entries in isolation.recovery_definitions(operator_password).items():
            definitions[section].extend(entries)
        command('exec', '-i', name, 'sh', '-c',
                'cat > /tmp/drill-definitions.json && rabbitmqctl -q import_definitions /tmp/drill-definitions.json',
                data=json.dumps(definitions).encode())

    def publish(channel, exchange, routing, event):
        channel.basic_publish(exchange, routing, json.dumps({'eventId': event}).encode(), mandatory=True,
                              properties=pika.BasicProperties(message_id=event, delivery_mode=2))

    def record(channel, receipts):
        delivery, props, body = channel.basic_get(QUEUE, auto_ack=False)
        assert delivery is not None and json.loads(body)['eventId'] == props.message_id
        receipts.execute('insert into receipts values (?)', (props.message_id,))
        channel.basic_ack(delivery.delivery_tag)

    def seconds(since):
        return round(time.monotonic() - since, 3)

    try:
        original, port = create('-original')
        with connect(port) as admin, sqlite3.connect(':memory:') as receipts:
            receipts.execute('create table receipts (id text primary key)')
            restore(original)
            channel = admin.channel()
            channel.confirm_delivery()
            event = str(uuid.uuid4())
            publish(channel, '', DLQ, event)
            since = time.monotonic()
            channel.queue_unbind(**BINDING)
            with connect(port, isolation.RECOVERY_USER, operator_password) as operator:
                try:
                    recovery.replay(operator.channel(), exchange=recovery.RETRY_EXCHANGE, queue=QUEUE, dlq=DLQ, limit=1)
                except pika.exceptions.UnroutableError:
                    result['route_failure_detected_s'] = seconds(since)
                else:
                    raise AssertionError('Missing route did not block replay')
            assert channel.queue_declare(DLQ, passive=True).method.message_count == 1
            channel.queue_bind(**BINDING)
            with connect(port, isolation.RECOVERY_USER, operator_password) as operator:
                assert recovery.replay(operator.channel(), exchange=recovery.RETRY_EXCHANGE,
                                       queue=QUEUE, dlq=DLQ, limit=1).replayed == 1
            record(channel, receipts)
            result['route_recovery_s'] = seconds(since)

            events = [str(uuid.uuid4()) for _ in range(count)]
            for event in events:
                publish(channel, isolation.EVENTS, 'extraction.completed', event)
            for _ in range(count // 2):
                record(channel, receipts)
            already_processed = count // 2
            assert channel.queue_declare(QUEUE, passive=True).method.message_count == count - already_processed
            admin.close()
            since = time.monotonic()
            command('kill', original)
            containers.remove(original)
            replacement, port = create('-empty')
            with connect(port) as new:
                result['empty_broker_ready_s'] = seconds(since)
                restore(replacement)
                result['definitions_ready_s'] = seconds(since)
                channel = new.channel()
                channel.confirm_delivery()
                assert channel.queue_declare(QUEUE, passive=True).method.message_count == 0
                pending = [event for event in events if not receipts.execute(
                    'select 1 from receipts where id=?', (event,)).fetchone()]
                assert len(pending) == count - already_processed
                result['reconciliation_ready_s'] = seconds(since)
                for event in pending:
                    publish(channel, isolation.EVENTS, 'extraction.completed', event)
                record(channel, receipts)
                result['first_recovered_s'] = seconds(since)
                for _ in pending[1:]:
                    record(channel, receipts)
                assert channel.queue_declare(QUEUE, passive=True).method.message_count == 0
                assert receipts.execute('select count(*) from receipts').fetchone()[0] == count + 1
                result['backlog_drained_s'] = seconds(since)
                result['replayed'] = len(pending)
                result['duplicates'] = 0
        return result
    finally:
        for name in reversed(containers):
            command('stop', '-t', '1', name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker-host')
    parser.add_argument('--events', type=int, choices=range(2, 10001), default=30, metavar='2-10000')
    args = parser.parse_args()
    docker = ['docker'] + (['--host', args.docker_host] if args.docker_host else [])
    print(json.dumps(measure(docker, 'rabbitmq:4.1-management', args.events)))
