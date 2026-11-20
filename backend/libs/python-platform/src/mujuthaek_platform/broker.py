"""RabbitMQ 연결. 주소 예: amqp://mujuthaek:mq-pass@localhost:5672/"""

import os

import pika


def managed_topology() -> bool:
    """격리 배포는 운영자가 미리 만든 topology만 사용하며 런타임 선언 권한을 갖지 않아요."""
    value = os.getenv("MUJUTHAEK_MANAGED_TOPOLOGY", "false").strip().lower()
    if value not in {"", "0", "1", "false", "true"}:
        raise ValueError("MUJUTHAEK_MANAGED_TOPOLOGY must be true or false")
    return value in {"1", "true"}


def connect(url: str, *, heartbeat: int = 60, blocked_timeout: int | None = None) -> pika.BlockingConnection:
    params = pika.URLParameters(url)
    params.heartbeat = heartbeat
    params.connection_attempts = 3
    params.retry_delay = 2
    if blocked_timeout is not None:
        params.blocked_connection_timeout = blocked_timeout
    return pika.BlockingConnection(params)
