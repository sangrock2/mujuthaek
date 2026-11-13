# extraction

[파이프라인·계약](../../../docs/07-data-pipeline-and-contracts.md) · [로컬 실행](../../../docs/04-local-development.md) · [테스트](../../../docs/10-testing-and-quality.md)

Python 3.12 추출 워커입니다. 원본 이벤트와 문서를 읽고 구조화·검증·검수·판정 틀 생성 후 outbox에 결과를 기록합니다. `v2`, `rules`, `assemble`, `verify`, `model`은 실행 단계·분야별 처리이며 임의로 제거하면 안 됩니다.

이 폴더에서 `uv sync --frozen` 후 서비스별 환경을 설정합니다. `uv run python -m mujuthaek_extraction run`은 큐 소비·발행·검수 API를 시작합니다. 기본 검수 API 포트는 8092입니다. `auto` 모드는 설정에 따라 유료 모델을 호출할 수 있으므로 먼저 config와 model/factory를 확인합니다.

`recorded`는 저장 응답 재생, `standin`은 파일 교환 모드입니다. `EXTRACTION_METHOD=legacy`는 이전 해석 방식이며 유료 키가 있는 V2 실행과의 조합은 차단합니다. 정확한 제약은 `src/mujuthaek_extraction/config.py`, `method.py`, `model/factory.py`가 기준입니다.

오프라인 검사는 `uv run --frozen pytest -q`입니다. `scripts/pipeline_live.py` 등의 실모델 평가·재처리 도구는 일반 테스트와 다릅니다. 계약·법정동코드·공유 라이브러리의 상대 경로를 유지합니다.
