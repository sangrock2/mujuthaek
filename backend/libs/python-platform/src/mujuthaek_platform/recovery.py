"""Confirmed transfer out of a dead-letter queue for operators."""

import argparse
import os
from copy import copy
from dataclasses import dataclass

import pika

from mujuthaek_platform import broker

RETRY_EXCHANGE = "mujuthaek.extraction.retry"
RESULT_QUEUE = "mujuthaek.extraction.completed"
REPLAY_HEADER = "x-mujuthaek-replays"
MAX_REPLAYS = 3


@dataclass
class ReplayResult:
    replayed: int = 0
    parked: int = 0


def publish_persistent(channel, exchange, queue, body, properties):
    props = copy(properties) if properties is not None else pika.BasicProperties()
    props.delivery_mode = 2
    channel.basic_publish(exchange=exchange, routing_key=queue, body=body, properties=props, mandatory=True)


def replay(channel, *, exchange, queue, dlq, limit):
    if not 1 <= limit <= 100:
        raise ValueError("Replay limit must be between 1 and 100")
    channel.confirm_delivery()
    waiting = channel.queue_declare(queue=dlq, passive=True).method.message_count
    result = ReplayResult()
    for _ in range(min(waiting, limit)):
        delivery, properties, body = channel.basic_get(queue=dlq, auto_ack=False)
        if delivery is None:
            break
        props = copy(properties) if properties is not None else pika.BasicProperties()
        headers = dict(props.headers or {})
        # Corrupt replay metadata is parked instead of resetting the retry budget.
        count = headers.get(REPLAY_HEADER, 0)
        parked = type(count) is not int or not 0 <= count < MAX_REPLAYS
        if not parked:
            headers[REPLAY_HEADER] = count + 1
        props.headers = headers
        try:
            publish_persistent(channel, exchange, dlq if parked else queue, body, props)
        except (pika.exceptions.UnroutableError, pika.exceptions.NackError):
            channel.basic_nack(delivery.delivery_tag, requeue=True)
            raise
        # Other failures close the connection and requeue the unacknowledged delivery.
        channel.basic_ack(delivery.delivery_tag)
        if parked:
            result.parked += 1
        else:
            result.replayed += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, choices=range(1, 101), default=10, metavar="1-100")
    parser.add_argument("--apply", action="store_true", help="Move messages. By default only show the DLQ count.")
    args = parser.parse_args()
    url = os.environ.get("BROKER_RECOVERY_URL")
    if not url:
        parser.error("BROKER_RECOVERY_URL is required")
    try:
        with broker.connect(url, blocked_timeout=30) as connection:
            channel = connection.channel()
            dlq = RESULT_QUEUE + ".dlq"
            if not args.apply:
                count = channel.queue_declare(queue=dlq, passive=True).method.message_count
                print(f"Dead-letter queue ready: {count}.")
                return
            result = replay(channel, exchange=RETRY_EXCHANGE, queue=RESULT_QUEUE, dlq=dlq, limit=args.limit)
    except (pika.exceptions.AMQPError, OSError, ValueError):
        raise SystemExit("Replay interrupted. Check the queue and confirmed deliveries before retrying.") from None
    print(f"Replayed {result.replayed}; left in the dead-letter queue {result.parked}.")


if __name__ == "__main__":
    main()
