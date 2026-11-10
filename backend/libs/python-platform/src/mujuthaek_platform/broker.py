"""RabbitMQ 연결. 주소 예: amqp://mujuthaek:mq-pass@localhost:5672/"""

import pika


def connect(url: str, *, heartbeat: int = 60) -> pika.BlockingConnection:
    params = pika.URLParameters(url)
    params.heartbeat = heartbeat
    params.connection_attempts = 3
    params.retry_delay = 2
    return pika.BlockingConnection(params)
