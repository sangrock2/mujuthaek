"""파이썬 워커 공통 기술 코드. 업무 규칙은 넣지 않아요.

ids        uuid7()                          시간 순으로 정렬되는 ID (DB 기본 키)
events     new_event(type, producer, data)  모듈·프로그램 사이 이벤트 봉투
outbox     add(cur, event), relay_once()    저장과 같은 트랜잭션에 이벤트 기록 → RabbitMQ로 발행
broker     connect(url)                     RabbitMQ 연결
db         connect(url)                     PostgreSQL 연결
logging    setup(service)                   JSON 한 줄 로그
contracts  validate_event(event)            contracts/events/의 JSON 스키마로 이벤트 검사
slack      SlackNotifier.from_env().send()  슬랙 수신 웹훅으로 알림 (주소 없으면 보내지 않음, 실패는 SlackError)
"""
