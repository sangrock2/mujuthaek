"""extraction 워커 설정. 값은 환경 변수에서 읽고, 없으면 로컬 개발 값(infra/.env.example과 같은 값)을 씁니다.

모델 (결정 C12, 2026-10-15)
  EXTRACTION_MODEL_MODE=auto (기본)  로컬 AI를 먼저 쓰고, 연결이 안 되거나 결과가 부족하면 유료 API(gpt-6-luna)
  EXTRACTION_MODEL_MODE=recorded     녹화한 응답을 재생 (개발·시연용 가짜 추출기, 유료 호출 없음)
  EXTRACTION_MODEL_MODE=standin      요청을 파일로 쓰고 답 파일을 기다림(EXTRACTION_STANDIN_DIR, 대역 모델로 흐름 시험, 유료 호출 없음)
  LOCAL_AI_URL       로컬 AI 주소 (OpenAI 호환 /v1/chat/completions. 예: http://localhost:11434/v1). 비우면 로컬 AI 없음으로 보고 바로 유료 API
  OPENAI_API_KEY     유료 API 키. 환경 변수가 없으면 services/extraction/.env 파일에서 읽습니다. 키는 출력·저장하지 않습니다

유료 API 비용 줄이기 (2026-10-18, 끄면 이전 방식)
  OPENAI_SHARED_SCHEMA=true      모든 호출이 같은 출력 형식을 보내고 원문 끝에 캐시 지점을 둡니다(원문 캐시 읽기). false면 호출마다 형식
  OPENAI_LIGHT_CALLS=             추론 강도를 낮출 호출, 쉼표로(기본 빈 값 = 모두 OPENAI_REASONING_EFFORT).
                                 추론 강도가 다르면 원문 캐시를 따로 써서 공고마다 원문 캐시 쓰기 요금을 한 번 더 냅니다(2026-10-24 실측)
  OPENAI_LIGHT_EFFORT=low        위 호출의 추론 강도
  OPENAI_STREAM=true             응답을 스트리밍으로 받아, 받는 도중 반복 폭주가 보이면 끊습니다(남은 출력 요금 절약). false면 한 번에 받음
  EXTRACTION_REPAIR_MIN_BAD_ITEMS=3  형식이 틀린 항목이 이보다 적으면 다시 요청하지 않고 그 항목만 뺍니다(1이면 이전처럼 늘 다시 요청)

성공한 호출 다시 쓰기·누적 예산 (2026-10-20, model/call_cache.py)
  EXTRACTION_CALL_CACHE=true     성공한 모델 호출(정상 종료·출력 형식 통과)을 DB(extraction_call_cache)에 두고, 완전히 같은 요청이면 비용 없이 다시 씁니다.
                                 실패해 다시 처리할 때 성공했던 호출은 보내지 않습니다. 원문·프롬프트·형식·모델 설정이 하나라도 다르면 쓰지 않습니다.
                                 false면 이전처럼 매번 호출합니다
  EXTRACTION_CALL_CACHE_DAYS=90  이보다 오래된 저장 응답은 다시 처리 주기(retry_loop)·retry 명령이 지웁니다
  EXTRACTION_NOTICE_BUDGET_USD   공고(원본 버전) 1건 유료 비용 상한. 실패해 다시 처리해도 앞선 처리가 쓴 비용부터 셉니다(처리마다 새 예산이 아님)

병렬 호출 (2026-10-20, extract.py)
  EXTRACTION_PARALLEL_CALLS=4    구조 호출이 끝난 뒤 나머지 섹션 호출(일정·자격·선정·서류 등)을 이 수만큼 동시에 보냅니다.
                                 결과는 순서대로 부른 것과 같게 모으고, 예산은 동시에 나간 호출까지 합쳐 상한을 지킵니다. 1이면 이전처럼 하나씩
  EXTRACTION_PARALLEL_STAGGER_SECONDS=1.5  병렬 섹션 호출을 이 간격(초)으로 하나씩 내보냅니다(한꺼번에 보내면 1개가 원문 캐시를 못 읽음).
                                 응답은 기다리지 않아 늘어나는 시간은 최대 (호출 수-1)×간격. 0이면 한꺼번에

비용 경고 (2026-10-23, cost_alert.py)
  EXTRACTION_SLACK_WEBHOOK_URL   슬랙 수신 웹훅 주소(없으면 services/extraction/.env에서 읽음). 이 이름이 어디에도 없으면
                                 팀 공통 이름 SLACK_WEBHOOK_URL을 같은 순서(환경 변수 → .env)로 찾습니다.
                                 전송은 공통 라이브러리 mujuthaek_platform.slack이 합니다(다른 워커도 같이 씀).
                                 이번 달 유료 비용이 EXTRACTION_MONTHLY_BUDGET_USD의 80%를 넘으면 달마다 한 번 보냅니다.
                                 비우면 보내지 않고 경고 로그만 남깁니다. 주소는 출력·로그에 남기지 않습니다

호출별 출력 한도 (2026-10-20, rules/housing_notice OUTPUT_LIMITS)
  EXTRACTION_MAX_OUTPUT_TOKENS   비우면 기본 한도(실측 최대의 약 1.3배). "selection=32000,documents=24000"처럼 호출 이름=토큰 수로 바꿉니다.
                                 바꾸면 그 호출은 성공한 호출 다시 쓰기의 요청 열쇠가 달라져 한 번 새로 호출합니다
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from mujuthaek_extraction.method import extraction_method
from mujuthaek_platform.slack import read_env_value

SERVICE_DIR = Path(__file__).resolve().parents[2]
LOCAL_S3_ENDPOINT = "http://127.0.0.1:9000"  # infra/docker-compose.yml의 MinIO
LOCAL_S3_KEYS = ("minio", "minio-pass")  # infra/.env.example의 MINIO_ROOT_USER·MINIO_ROOT_PASSWORD
MODEL_MODES = {"auto", "recorded", "standin"}
SLACK_WEBHOOK_ENV_NAMES = ("EXTRACTION_SLACK_WEBHOOK_URL", "SLACK_WEBHOOK_URL")  # 서비스 전용 이름 먼저(이전 이름 유지), 공통 이름은 나중


@dataclass(frozen=True)
class Settings:
    """extraction 워커 전체가 함께 쓰는 설정 값 묶음입니다. 각 칸의 환경 변수는 from_env를 보면 됩니다."""

    db_url: str
    rabbitmq_url: str
    s3_endpoint: str | None
    s3_bucket: str
    s3_access_key: str | None
    s3_secret_key: str | None
    model_mode: str = "auto"
    local_ai_url: str | None = None
    local_ai_model: str = "local"
    openai_model: str = "gpt-6-luna"
    openai_effort: str = "medium"
    openai_shared_schema: bool = True
    openai_light_calls: tuple[str, ...] = ()  # 비움(2026-10-24): 추론 강도가 다르면 캐시가 나뉘어 원문을 두 번 씀
    openai_light_effort: str = "low"
    openai_stream: bool = True  # 2026-10-24: 폭주를 받는 도중 끊음(실측 4차: 출력의 22%가 폭주로 버린 글)
    env_file: Path = SERVICE_DIR / ".env"
    recorded_dir: Path | None = None  # recorded 모드: <호출 이름>.json (응답 문자열 목록) 파일이 있는 폴더
    standin_dir: Path | None = None  # standin 모드: 요청·답 파일을 주고받을 폴더(model/file_exchange.py)
    require_pdf: bool = True  # 공고는 PDF가 반드시 옴(2026-10-16). false는 글자만 있는 시험 이벤트용
    extraction_method: str = "structured"  # 롤백 스위치(method.py): structured(표 머리글 복원) / legacy(이전 방식)
    local_files_dir: Path | None = None  # 시험용: 첨부를 S3 대신 이 폴더에서 읽음 (s3Key = 폴더 아래 상대 경로)
    notice_budget_usd: float = 0.5  # 공고 1건 유료 비용 상한. 큰 공고가 중간에 멈추지 않게 넉넉히(실제 $0.03~0.06, 사용자 결정 2026-10-16)
    daily_budget_usd: float = 30.0  # 유료 비용 하루 전체 상한(한국 시간 기준, 사용자 결정 2026-10-21). 넘을 처리는 다음 날까지 미룹니다
    monthly_budget_usd: float = 600.0  # 유료 비용 월 전체 상한(사용자 결정 2026-10-21)
    slack_webhook_url: str | None = field(default=None, repr=False)  # 월 상한 80% 경고 (EXTRACTION_SLACK_WEBHOOK_URL, 비우면 로그만)
    review_host: str = "127.0.0.1"  # 검수 API에는 인증이 없어 기본은 이 컴퓨터에서만 열립니다 (Docker에서는 0.0.0.0)
    review_port: int = 8092
    review_token: str | None = None  # 있으면 검수 API에 Bearer 토큰 필요, 없으면 같은 컴퓨터 요청만 (로그에 남기지 않음)
    review_db_pool: int = 8  # 검수 API DB 연결 풀 최대 (EXTRACTION_REVIEW_DB_POOL). 넘는 요청은 빈 연결을 기다려요
    relay_seconds: float = 2.0
    retry_seconds: float = 300  # 자료 대기·실패 다시 처리 간격의 기준(5분 → 10분 → 20분 …)
    max_attempts: int = 6  # 이벤트 하나를 처리하는 최대 횟수
    region_table: Path = SERVICE_DIR / "data" / "legal-dong-codes" / "legal_dong_20260929.csv"
    region_table_date: str = "2026-09-29"
    call_cache: bool = True  # 성공한 호출 다시 쓰기 (EXTRACTION_CALL_CACHE)
    call_cache_days: int = 90  # 저장 응답 보관 일수 (EXTRACTION_CALL_CACHE_DAYS)
    parallel_calls: int = 4  # 구조 호출 뒤 동시에 보낼 섹션 호출 수 (EXTRACTION_PARALLEL_CALLS, 1이면 하나씩)
    parallel_stagger_seconds: float = 1.5  # 병렬 섹션 호출을 내보내는 간격 (EXTRACTION_PARALLEL_STAGGER_SECONDS, 0이면 한꺼번에)
    # 주거·이주 혜택(BENEFIT) 정제를 켤지 (EXTRACTION_BENEFIT_ENABLED). 2026-10-25 추가. 켜면 쌓인 정책(로컬 온통청년만 3천여 건)이
    # 유료 AI를 타므로 배포 때 사람이 켭니다. 꺼져 있으면 이전처럼 BENEFIT 이벤트를 받고 넘깁니다
    benefit_enabled: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        """환경 변수에서 설정을 읽습니다. 모델 모드가 틀리거나 운영(EXTRACTION_ENV=production)에 필수 값이 없으면 ValueError를 냅니다."""
        endpoint = os.getenv("S3_ENDPOINT", LOCAL_S3_ENDPOINT) or None  # 빈 값이면 AWS S3 (인증은 EC2 역할)
        access_key, secret_key = LOCAL_S3_KEYS if endpoint else (None, None)
        mode = os.getenv("EXTRACTION_MODEL_MODE", "auto")
        if mode not in MODEL_MODES:
            raise ValueError(f"EXTRACTION_MODEL_MODE는 {sorted(MODEL_MODES)} 중 하나여야 합니다: {mode!r}")
        recorded = os.getenv("EXTRACTION_RECORDED_DIR")
        if os.getenv("EXTRACTION_ENV", "").lower() == "production":
            # 운영에서는 개발용 기본값(로컬 DB·MinIO·개발 비밀번호)으로 조용히 돌지 않게 필수 값을 확인합니다(검토 2026-10-16)
            missing = [name for name in ("DB_URL", "RABBITMQ_URL", "S3_BUCKET", "EXTRACTION_REVIEW_TOKEN") if not os.getenv(name)]
            if "S3_ENDPOINT" not in os.environ:
                missing.append("S3_ENDPOINT(AWS S3면 빈 값)")
            if missing:
                raise ValueError("운영(EXTRACTION_ENV=production)에 필요한 설정이 없습니다: " + ", ".join(missing))
        return cls(
            db_url=os.getenv("DB_URL", "postgresql://extraction_app:extraction-pass@127.0.0.1:5432/extraction"),
            rabbitmq_url=os.getenv("RABBITMQ_URL", "amqp://mujuthaek:mq-pass@127.0.0.1:5672/"),
            s3_endpoint=endpoint,
            s3_bucket=os.getenv("S3_BUCKET", "mujuthaek-raw"),
            s3_access_key=os.getenv("AWS_ACCESS_KEY_ID") or access_key,
            s3_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY") or secret_key,
            model_mode=mode,
            local_ai_url=os.getenv("LOCAL_AI_URL") or None,
            local_ai_model=os.getenv("LOCAL_AI_MODEL", "local"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-6-luna"),
            openai_effort=os.getenv("OPENAI_REASONING_EFFORT", "medium"),
            openai_shared_schema=os.getenv("OPENAI_SHARED_SCHEMA", "true").lower() != "false",
            openai_light_calls=tuple(n.strip() for n in os.getenv("OPENAI_LIGHT_CALLS", "").split(",") if n.strip()),
            openai_light_effort=os.getenv("OPENAI_LIGHT_EFFORT", "low"),
            openai_stream=os.getenv("OPENAI_STREAM", "true").lower() != "false",
            recorded_dir=Path(recorded) if recorded else None,
            standin_dir=Path(os.environ["EXTRACTION_STANDIN_DIR"]) if os.getenv("EXTRACTION_STANDIN_DIR") else None,
            require_pdf=os.getenv("EXTRACTION_REQUIRE_PDF", "true").lower() != "false",
            extraction_method=extraction_method(),
            local_files_dir=Path(os.environ["EXTRACTION_LOCAL_FILES_DIR"]) if os.getenv("EXTRACTION_LOCAL_FILES_DIR") else None,
            notice_budget_usd=float(os.getenv("EXTRACTION_NOTICE_BUDGET_USD", "0.5")),
            daily_budget_usd=float(os.getenv("EXTRACTION_DAILY_BUDGET_USD", "30")),
            monthly_budget_usd=float(os.getenv("EXTRACTION_MONTHLY_BUDGET_USD", "600")),
            slack_webhook_url=read_env_value(SLACK_WEBHOOK_ENV_NAMES, SERVICE_DIR / ".env"),
            review_host=os.getenv("EXTRACTION_REVIEW_HOST", "127.0.0.1"),
            review_port=int(os.getenv("EXTRACTION_REVIEW_PORT", "8092")),
            review_token=os.getenv("EXTRACTION_REVIEW_TOKEN") or None,
            review_db_pool=int(os.getenv("EXTRACTION_REVIEW_DB_POOL", "8")),
            relay_seconds=float(os.getenv("EXTRACTION_RELAY_SECONDS", "2")),
            retry_seconds=float(os.getenv("EXTRACTION_RETRY_SECONDS", "300")),
            max_attempts=int(os.getenv("EXTRACTION_MAX_ATTEMPTS", "6")),
            call_cache=os.getenv("EXTRACTION_CALL_CACHE", "true").lower() != "false",
            call_cache_days=int(os.getenv("EXTRACTION_CALL_CACHE_DAYS", "90")),
            parallel_calls=max(1, int(os.getenv("EXTRACTION_PARALLEL_CALLS", "4"))),
            parallel_stagger_seconds=max(0.0, float(os.getenv("EXTRACTION_PARALLEL_STAGGER_SECONDS", "1.5"))),
            benefit_enabled=os.getenv("EXTRACTION_BENEFIT_ENABLED", "false").lower() == "true",
        )

    def openai_api_key(self) -> str | None:
        """환경 변수 → .env 파일 순서로 찾습니다. 돌려주기만 하고 출력하지 않습니다."""
        from mujuthaek_extraction.model.openai_responses import read_api_key

        return os.getenv("OPENAI_API_KEY") or (read_api_key(self.env_file) if self.env_file.exists() else None)
