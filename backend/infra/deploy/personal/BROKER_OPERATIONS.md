# RabbitMQ 적체 확인과 실패 큐 복구

## 적체 확인

운영 호스트에서 `sudo python3 broker_status.py`를 실행합니다. 명령은 브로커 큐를 소비하지 않고 PostgreSQL은 읽기 전용으로 조회합니다. 메시지 본문, 이벤트별 데이터, 자격증명은 출력 대상에서 제외합니다.

```bash
sudo python3 broker_status.py > broker-before.json
sudo python3 broker_status.py --previous broker-before.json > broker-now.json
```

- `ready`는 소비자에게 전달되기 전인 건수, `unacked`는 전달됐지만 ACK가 오지 않은 건수입니다. `outstanding_delta_per_minute`는 두 값 합계의 순변화량입니다. 유입과 완료가 동시에 일어나므로 순변화량과 처리율은 별개입니다.
- `head_age_seconds`는 RabbitMQ가 큐 맨 앞 메시지의 시각을 제공할 때 계산합니다. 기존 메시지에 시각 속성이 없거나 브로커가 해당 값을 제공하지 않으면 `null`입니다.
- 추출 DB의 공고 처리 기록과 정책 결과 Outbox 생성 건수는 최근 15분을 집계합니다. 정책 결과의 생성 건수에는 검수 후 발행도 포함됩니다. 최근 24시간 공고 추출 실패 사유는 API 잔액 부족, 앱 예산 상한, 시간 초과, 기타로 집계합니다.
- Outbox별 미발행 건수, 최대 발행 시도 횟수와 가장 오래된 미발행 건의 대기 시간을 봅니다. 입력 큐가 늘고 Outbox가 비어 있으면 소비자와 추출 의존성부터 점검합니다. Outbox 대기 시간이 늘면 브로커 연결·라우팅부터 점검합니다.

## 실패 큐 재처리

원인을 수정한 뒤 한 번에 최대 100건까지 실행합니다. 기본 한도는 10건입니다. 발행 확인과 필수 라우팅을 함께 사용하므로 대상 큐가 메시지를 받았다는 확인이 온 뒤에만 원본을 ACK합니다. 재처리 한도 3회에 도달한 메시지는 확인을 거쳐 실패 큐에 남깁니다. 발행 확인 뒤 ACK 전에 연결이 끊기면 중복 전달될 수 있으므로 기존 이벤트 ID를 유지합니다.

### 기존 격리 배포에 적용

1. `python3 service_isolation.py prepare-recovery --out <비공개_새_디렉터리>`로 구성 파일을 만듭니다. 파일이 나가는 위치는 운영 호스트의 비공개 작업 경로를 사용합니다.
2. `broker-recovery-routes.json`의 바인딩과 추출기 토픽 권한을 운영 브로커의 영속 정의에 합치고 RabbitMQ 정의를 가져옵니다. 이 변경을 추출 워커 교체보다 먼저 적용합니다. 기존 큐 종류·큐 인자·데이터 볼륨을 보존합니다.
3. API 결과 큐에 대한 복구가 필요할 때만 `broker-recovery.json`을 가져옵니다. 계정은 API 결과 실패 큐를 읽고 결과 큐와 해당 실패 큐로만 발행할 수 있습니다. 추출 런타임 계정은 이 경로로 발행할 수 없습니다.
4. 새 추출 이미지의 Python 런타임을 운영 브로커의 내부 Docker 네트워크에서 일회성 컨테이너로 실행합니다. `--env-file`로 비공개 `recovery.env`를 넘기고 `python -m mujuthaek_platform.recovery`로 대기 건수를 확인합니다. 실제 이동에는 `--apply --limit 10`을 붙입니다.
5. 작업을 마치면 RabbitMQ에서 `mujuthaek-api-recovery` 계정을 삭제합니다. 다음 복구에서는 새 임시 자격증명을 생성합니다. 일반 서비스 정의에는 이 임시 계정을 합치지 않습니다.

추출 입력은 해당 워커의 `python -m mujuthaek_extraction replay-dlq --queue notice --limit 10` 또는 `--queue policy`로 처리합니다. 운영 API 결과 재처리에는 위 임시 계정의 명령을 사용합니다. 제공자 잔액 부족이나 예산 상한으로 멈춘 메시지는 한도가 해소되었는지 먼저 확인합니다.

데이터 볼륨 전체가 손실되면 단일 브로커의 큐 자체는 복구할 별도 복제본이 없습니다. DB 기반 후속 작업 유실과 노드·볼륨 장애 대응은 별도의 검증 범위입니다.
