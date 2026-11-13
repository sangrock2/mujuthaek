# mujuthaek-platform

[공유 코드 상세](../../../docs/reference/python-platform.md) · [파이프라인](../../../docs/07-data-pipeline-and-contracts.md)

collector·extraction이 함께 사용하는 DB·RabbitMQ·outbox·이벤트·식별자·JSON 로그·운영 알림 기술 코드입니다. 업무별 추출·판정 규칙은 넣지 않습니다.

각 워커의 pyproject에서 `../../libs/python-platform`을 editable dependency로 참조합니다. 이 폴더에서 `uv run --frozen pytest -q`, `uv run ruff check`, `uv run ruff format --check`로 검사합니다.

outbox는 업무 저장과 같은 트랜잭션에서 추가하고 수신 측의 중복 처리를 전제로 최소 한 번 발행합니다. 함수·테이블·사용 예시는 상세 문서에 보존했습니다.
