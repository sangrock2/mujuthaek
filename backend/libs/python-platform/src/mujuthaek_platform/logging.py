"""JSON 한 줄 로그. CloudWatch에서 칸으로 검색할 수 있게 extra 값도 칸으로 넣어요.

  log.info("수집 끝", extra={"source": "dcco", "new": 3})
  → {"time": "...", "level": "INFO", "service": "collector", "logger": "...",
     "message": "수집 끝", "source": "dcco", "new": 3}

사용자 소득·자산·나이 같은 값은 extra에도 넣지 않아요 (팀 규칙).
"""

import json
import logging
import sys
from datetime import UTC, datetime

_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, UTC)
        data = {
            "time": created.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        data.update({k: v for k, v in vars(record).items() if k not in _STANDARD and not k.startswith("_")})
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def setup(service: str, level: int | str = logging.INFO) -> None:
    """루트 로거를 JSON 한 줄 출력으로 바꿔요. 여러 번 불러도 핸들러가 겹치지 않아요."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("pika", "httpx", "httpcore", "botocore", "boto3", "urllib3", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
