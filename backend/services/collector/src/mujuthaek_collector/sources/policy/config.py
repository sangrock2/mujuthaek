"""정책 수집 설정. 인증키는 환경 변수로만 받아요 (저장소·로그에 남기지 않음).

DATA_GO_KR_SERVICE_KEY   공공데이터포털 인증키 (보조금24·복지로 중앙·복지로 지자체·K-Startup). API마다 활용신청이 따로 필요해요
YOUTHCENTER_API_KEY      온통청년 인증키 (youthcenter.go.kr 마이페이지에서 발급)
BIZINFO_API_KEY          기업마당 인증키 (bizinfo.go.kr 정책정보 개방 API에서 발급)
POLICY_YOUTH_CATEGORIES  온통청년 정책 대분류로 좁혀 받기, 쉼표로 (기본 빈 값 = 전체를 받고 수집기가 주거·창업을 골라요)
POLICY_DETAIL_LIMIT      한 회차에 상세·첨부를 처리하는 최대 정책 수 (나머지는 다음 회차)
POLICY_API_DELAY_SECONDS 같은 API 도메인 요청 간격
POLICY_MAX_FILES         정책 하나에서 받는 첨부 최대 수
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PolicySettings:
    data_go_kr_key: str | None = None
    youth_key: str | None = None
    bizinfo_key: str | None = None
    youth_categories: list[str] = field(default_factory=list)
    detail_limit: int = 300
    api_delay_seconds: float = 1.0
    max_pages: int = 100  # 목록을 최대 몇 페이지까지 (보조금24 1000건 × 100)
    max_files: int = 5
    max_origin_pages: int = 2  # 첨부가 없을 때 열어볼 원문 화면 수
    keep_months: int = 12  # 첨부 원본 보관 기간 (정책은 해마다 다시 공고돼요)

    @classmethod
    def from_env(cls) -> "PolicySettings":
        categories = os.getenv("POLICY_YOUTH_CATEGORIES", "")
        return cls(
            data_go_kr_key=os.getenv("DATA_GO_KR_SERVICE_KEY") or None,
            youth_key=os.getenv("YOUTHCENTER_API_KEY") or None,
            bizinfo_key=os.getenv("BIZINFO_API_KEY") or None,
            youth_categories=[c.strip() for c in categories.split(",") if c.strip()],
            detail_limit=int(os.getenv("POLICY_DETAIL_LIMIT", "300")),
            api_delay_seconds=float(os.getenv("POLICY_API_DELAY_SECONDS", "1.0")),
            max_files=int(os.getenv("POLICY_MAX_FILES", "5")),
        )
