"""수집기 설정. 값은 환경 변수에서 읽고, 없으면 로컬 개발 값(infra/.env.example과 같은 값)을 써요.

그래서 로컬에서는 `make infra`로 PostgreSQL·RabbitMQ·MinIO만 띄우면 환경 변수 없이 바로 실행돼요.
AWS로 옮길 때는 DB_URL·RABBITMQ_URL을 주고 S3_ENDPOINT를 빈 값("")으로 주면 AWS S3를 써요(인증은 EC2 역할).
"""

import os
from dataclasses import dataclass

LOCAL_S3_ENDPOINT = "http://localhost:9000"  # infra/docker-compose.yml의 MinIO
LOCAL_S3_KEYS = ("minio", "minio-pass")  # infra/.env.example의 MINIO_ROOT_USER·MINIO_ROOT_PASSWORD

USER_AGENT = os.getenv(
    "COLLECTOR_USER_AGENT",
    "MujuthaekBot/0.1 (+https://github.com/prgrms-be-devcourse/NBE11-13-final-Team02)",
)


@dataclass(frozen=True)
class Settings:
    db_url: str
    rabbitmq_url: str
    s3_endpoint: str | None
    s3_bucket: str
    s3_access_key: str | None = None  # 비우면 boto3 기본 인증 (AWS에서는 EC2 역할)
    s3_secret_key: str | None = None
    delay_seconds: float = 4.0  # 같은 도메인 요청 간격
    max_pages: int = 5  # 목록을 최대 몇 페이지까지 볼지
    since_days: int = 365  # 이보다 오래된 글은 열지 않음
    detail_limit: int = 20  # 한 회차에 상세를 여는 최대 글 수 (나머지는 다음 회차)
    max_file_bytes: int = 30 * 1024 * 1024
    empty_alert: int = 3  # 목록 0건이 이만큼 연속이면 구조 변경 경고
    parallel_sources: int = 4  # 게시판 출처를 동시에 몇 개까지 수집할지 (출처마다 도메인이 달라 요청 간격은 그대로)
    # 처음 수집 개수 제한 (core/intake.py): 처음 한 번 묶음마다 최신 몇 개만 AI 추출로 보낼지 (2026-10-27 결정)
    intake_housing_lh: int = 10  # LH 주거 공고
    intake_housing_other: int = 10  # LH 말고 다른 게시판 주거 공고 (합쳐서)
    intake_space: int = 10  # 사업공간 모집
    intake_policy: int = 500  # 지원 정책 (혜택·창업 지원, 출처 합쳐서)

    @property
    def intake_limits(self) -> dict[str, int]:
        return {
            "HOUSING_LH": self.intake_housing_lh,
            "HOUSING_OTHER": self.intake_housing_other,
            "SPACE": self.intake_space,
            "POLICY": self.intake_policy,
        }

    @classmethod
    def from_env(cls) -> "Settings":
        endpoint = os.getenv("S3_ENDPOINT", LOCAL_S3_ENDPOINT) or None  # 기본은 로컬 MinIO, 빈 값이면 AWS S3
        access_key, secret_key = LOCAL_S3_KEYS if endpoint else (None, None)
        return cls(
            db_url=os.getenv("DB_URL", "postgresql://collector_app:collector-pass@localhost:5432/collector"),
            # localhost면 pika가 IPv6(::1)부터 시도해 거절 오류 로그를 남겨요. RabbitMQ는 127.0.0.1에만 열려 있어요
            rabbitmq_url=os.getenv("RABBITMQ_URL", "amqp://mujuthaek:mq-pass@127.0.0.1:5672/"),
            s3_endpoint=endpoint,
            s3_bucket=os.getenv("S3_BUCKET", "mujuthaek-raw"),
            s3_access_key=os.getenv("AWS_ACCESS_KEY_ID") or access_key,
            s3_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY") or secret_key,
            delay_seconds=float(os.getenv("COLLECTOR_DELAY_SECONDS", "4.0")),
            max_pages=int(os.getenv("COLLECTOR_MAX_PAGES", "5")),
            since_days=int(os.getenv("COLLECTOR_SINCE_DAYS", "365")),
            detail_limit=int(os.getenv("COLLECTOR_DETAIL_LIMIT", "20")),
            parallel_sources=max(1, int(os.getenv("COLLECTOR_PARALLEL_SOURCES", "4"))),
            intake_housing_lh=int(os.getenv("COLLECTOR_INTAKE_HOUSING_LH", "10")),
            intake_housing_other=int(os.getenv("COLLECTOR_INTAKE_HOUSING_OTHER", "10")),
            intake_space=int(os.getenv("COLLECTOR_INTAKE_SPACE", "10")),
            intake_policy=int(os.getenv("COLLECTOR_INTAKE_POLICY", "500")),
        )
