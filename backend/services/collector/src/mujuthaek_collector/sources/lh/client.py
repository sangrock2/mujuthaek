"""LH 수집용 요청 클라이언트: 공공데이터 API 공통 클라이언트(PublicDataClient)에 LH에만 필요한 예외 하나를 더해요.

- robots.txt 예외: config.ROBOTS_OVERRIDES에 적은 경로(LH 상세정보 API가 알려주는 첨부 주소)만 허용해요.
  나머지 주소는 공통 클라이언트 그대로 robots.txt를 지켜요. 예외를 쓸 때마다 로그를 남겨요.
- 공공데이터포털 API(apis.data.go.kr)는 0.5초 간격으로 불러요 (PublicDataClient). 기관 사이트는 팀 기본 간격 그대로예요.

공통 클라이언트가 도메인별 간격과 예외 목록을 받게 되면 이 파일은 지워요.
"""

from __future__ import annotations

import logging
import urllib.parse

from mujuthaek_collector.sources.lh import config
from mujuthaek_collector.sources.public_data import PublicDataClient

log = logging.getLogger(__name__)


class LhClient(PublicDataClient):
    api_hosts = (config.API_HOST,)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.robots_overridden = 0

    def allowed(self, url: str) -> bool:
        if any(url.startswith(prefix) for prefix in config.ROBOTS_OVERRIDES):
            self.robots_overridden += 1
            log.info("robots.txt 예외 경로로 요청", extra={"source": "lh", "path": urllib.parse.urlsplit(url).path})
            return True
        return super().allowed(url)
