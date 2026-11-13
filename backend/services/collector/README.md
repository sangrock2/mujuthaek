# collector

[파이프라인](../../../docs/07-data-pipeline-and-contracts.md) · [출처·CLI·운영 상세](../../../docs/reference/collector-operations.md) · [LH 어댑터](src/mujuthaek_collector/sources/lh/README.md)

Python 3.12 수집 워커입니다. 원본·첨부·버전을 저장하고 outbox로 이벤트를 발행합니다. `../../libs/python-platform`을 공통 기술 패키지로 사용합니다.

이 폴더에서 `uv sync --frozen`, `uv run python -m mujuthaek_collector run`으로 실행합니다. 실제 수집은 외부 기관 요청·저장·발행을 수행합니다. 인프라·DB 마이그레이션·환경변수 준비는 [로컬 문서](../../../docs/04-local-development.md)를 먼저 봅니다.

일반 오프라인 검사는 `uv run --frozen pytest -q`입니다. 별도 DB 설정이 필요한 검사는 [테스트 문서](../../../docs/10-testing-and-quality.md)와 상세 안내에서 구분합니다.
