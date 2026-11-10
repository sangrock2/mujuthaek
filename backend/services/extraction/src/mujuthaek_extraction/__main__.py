"""extraction 워커 실행 명령 (services/extraction에서 uv run python -m mujuthaek_extraction ...).

  run                    큐 소비 + 아웃박스 발행(2초) + 검수 API(:8092). 운영·Docker 기본 명령
  process-file <파일>    raw.notice.collected 이벤트 파일 1건을 큐 없이 처리하고 저장
  retry                  WAITING_SOURCE·FAILED로 끝난 이벤트를 다시 처리 (보관 기간이 지난 호출 캐시도 지움)
  relay                  아웃박스에 쌓인 이벤트를 한 번 발행
  review-api             검수 API만 실행
  declare                큐·교환기만 선언
  replay-dlq [--queue notice|policy] [--limit N]
                         .dlq 메시지를 원래 큐로 되돌림 (원인을 고친 뒤 실행, 기본 policy·100건)

모델: 기본은 로컬 AI → (연결 안 됨·결과 부족) → 유료 API. 녹화 응답 재생은 EXTRACTION_MODEL_MODE=recorded (config.py 참고)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mujuthaek_extraction.config import Settings
from mujuthaek_platform import broker, db, outbox
from mujuthaek_platform import logging as platform_logging
from mujuthaek_platform.events import new_event


def main() -> None:
    """명령행 인자를 읽어 선택한 하위 명령(run·process-file·retry·relay·review-api·declare·replay-dlq)을 실행합니다."""
    parser = argparse.ArgumentParser(prog="mujuthaek_extraction")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run")
    file_command = commands.add_parser("process-file")
    file_command.add_argument("path", type=Path)
    commands.add_parser("retry")
    commands.add_parser("relay")
    commands.add_parser("review-api")
    commands.add_parser("declare")
    replay_command = commands.add_parser("replay-dlq")
    replay_command.add_argument("--queue", choices=["notice", "policy"], default="policy")
    replay_command.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    platform_logging.setup("extraction")
    settings = Settings.from_env()
    from mujuthaek_extraction import worker

    if args.command == "run":
        worker.run(settings)
    elif args.command == "process-file":
        raw_event = json.loads(args.path.read_text(encoding="utf-8"))
        with worker.store_session(settings) as store:
            try:
                job_id = worker.Processor(settings).handle(store, raw_event)
            except worker.ClaimBusy:
                print("같은 원본 버전을 다른 처리가 하고 있습니다. 끝난 뒤 다시 실행하세요.")
                return
        print(job_id or "이미 처리한 이벤트입니다.")
    elif args.command == "retry":
        processor = worker.Processor(settings)
        with worker.store_session(settings) as store:
            worker.purge_call_cache(settings, store)
            events = store.retryable_events(max_attempts=settings.max_attempts)
            busy = 0
            for raw_event in events:
                try:
                    processor.handle(store, raw_event)
                except worker.ClaimBusy:
                    busy += 1  # 다른 처리가 하고 있음: 그 처리가 결과를 남깁니다
        print(f"다시 처리 {len(events) - busy}건" + (f", 다른 처리 중이라 건너뜀 {busy}건" if busy else ""))
    elif args.command == "relay":
        conn = db.connect(settings.db_url)
        conn.autocommit = True
        connection = broker.connect(settings.rabbitmq_url)
        channel = outbox.open_channel(connection)
        print(f"발행 {outbox.relay_once(conn, channel)}건")
        connection.close()
        conn.close()
    elif args.command == "review-api":
        from mujuthaek_extraction.review_api import ReviewService, serve

        server = serve(
            ReviewService(lambda: worker.store_session(settings), new_event, settings.monthly_budget_usd), settings.review_host, settings.review_port
        )
        server.serve_forever()
    elif args.command == "declare":
        connection = broker.connect(settings.rabbitmq_url)
        worker.declare(connection.channel())
        connection.close()
    elif args.command == "replay-dlq":
        dlq, queue = worker.DLQ_TARGETS[args.queue]
        connection = broker.connect(settings.rabbitmq_url)
        channel = connection.channel()
        worker.declare(channel)
        print(f"{dlq} → {queue} 되돌림 {worker.replay_dlq(channel, dlq, queue, args.limit)}건")
        connection.close()


if __name__ == "__main__":
    main()
