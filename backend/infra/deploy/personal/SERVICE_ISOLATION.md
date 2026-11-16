# 선택적 MQ/S3 권한 분리 전환

기본 compose의 공유 키를 자동 변경하지 않는다. 이 도구는 네트워크 호출 없이 로컬 준비물과 제공된 스냅샷만 검사한다. 운영자가 제공하는 스냅샷은 실시간 권한 증명이 아니다.

1. `python service_isolation.py prepare --account <12자리계정> --bucket <버킷> --collector-user <기존mujuthaek-personal-runtime-이름> --out <새폴더>`로 준비한다. 파일은 최초 생성부터 비공개로 만들고 덮어쓰지 않는다.
2. `isolation-plan.json`의 사용자별 inline policy와 permissions boundary를 검토해 별도로 적용한다. 기존 collector 주체는 writer로 유지하고 API/추출은 별도 reader를 만든다. notification SES 주체와도 분리한다. 새 access key와 secret은 `.env.isolation`에 채운다.
3. RabbitMQ definitions를 검토해 별도 적용한다. 기존 topology와 인자 일치 여부를 먼저 확인한다. 서비스별 사용자 외 공유 `mujuthaek` 주체의 vhost 권한을 전환 시 회수한다. 운영 데이터/기존 큐를 삭제하지 않는다.
4. 새 계정별 전송·수신·DLQ 재처리와 타 서비스 routing key 거절, 기본 exchange 거절을 실제 브로커에서 확인한다. Python은 `MUJUTHAEK_MANAGED_TOPOLOGY=true`, Java는 `SPRING_RABBITMQ_DYNAMIC=false`로 선언 권한 없이 준비된 topology만 사용한다.
5. broker definitions export, IAM 증거 JSON, 격리 overlay를 병합한 Compose JSON을 준비한다. IAM 증거는 api/extraction/collector별 `user_arn`, `access_key_id`, `active_access_key_ids`, `attached_policies`, `groups`, `inline_policies`, `boundary_arn`, `boundary_policy`를 담는다. 각각 AWS 조회 결과에서 작성한다. Compose JSON과 export에도 비밀 정보가 있으므로 비공개 파일로 관리한다.
6. `python service_isolation.py readiness --bundle <준비폴더> --environment <.env.isolation> --broker-export <export.json> --iam-evidence <iam.json> --compose-config <config.json> --activation-file <새.env.activation>`을 실행한다. 실패하면 activation 파일을 생성하지 않는다. 이 검사는 네트워크를 사용하지 않는다.
7. 점검된 환경을 마지막 env-file로, `compose.prod.yml` 다음에 `compose.isolated.yml`을 명시해 별도 전환한다. overlay는 activation 표시/서비스별 키가 없으면 실패한다. 실제 IAM/MQ 거절 검사와 API PDF/지역 읽기, collector 원본 쓰기, extraction 읽기·재시도까지 통과한 후 이전 키를 회수한다.

이번 작업에서는 2~7의 실서비스 적용을 실행하지 않았다. 기본 배포 경로의 공유 자격 증명 위험은 실제 전환 전까지 남는다. 실패 시 무조건 이전 공유 키를 복원하는 자동화는 제공하지 않는다.
