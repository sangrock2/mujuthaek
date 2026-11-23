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

### 자동 적체 알림

`mujuthaek-broker-alerts.timer`를 운영 호스트에 설치하면 5분마다 주요 큐와 아웃박스를 읽기 전용으로 확인합니다. 실패 큐는 비어 있지 않으면 알리고, 소비자 없는 대기, 15분 이상 걸린 대기·미발행, 20건 이상으로 줄지 않는 대기는 연속 점검에서 확인되면 알립니다. 수동 보류 큐는 제외합니다. 동일 경고는 한 번 보내고 해소된 뒤 재발하면 다시 보냅니다.

설치 시 `broker_alerts.py`, `broker_status.py`, `slack_alerts.py`를 `/usr/local/lib/mujuthaek-broker-alerts`에 배치하고 `systemd/` 아래 두 파일을 `/etc/systemd/system`에 설치합니다. 웹훅은 root 전용 `/etc/mujuthaek-ops/slack-webhook`에 입력합니다. `systemctl start mujuthaek-broker-alerts.service`가 성공한 뒤 `systemctl enable --now mujuthaek-broker-alerts.timer`로 예약합니다. 앱 컨테이너 재시작이나 메시지 재처리는 필요하지 않습니다.

원인을 수정한 뒤 한 번에 최대 100건까지 실행합니다. 기본 한도는 10건입니다. 발행 확인과 필수 라우팅을 함께 사용하므로 대상 큐가 메시지를 받았다는 확인이 온 뒤에만 원본을 ACK합니다. 재처리 한도 3회에 도달한 메시지는 확인을 거쳐 실패 큐에 남깁니다. 발행 확인 뒤 ACK 전에 연결이 끊기면 중복 전달될 수 있으므로 기존 이벤트 ID를 유지합니다.

### 기존 격리 배포에 적용

1. `python3 service_isolation.py prepare-recovery --out <비공개_새_디렉터리>`로 구성 파일을 만듭니다. 파일이 나가는 위치는 운영 호스트의 비공개 작업 경로를 사용합니다.
2. `broker-recovery-routes.json`의 바인딩과 추출기 토픽 권한을 운영 브로커의 영속 정의에 합치고 RabbitMQ 정의를 가져옵니다. 이 변경을 추출 워커 교체보다 먼저 적용합니다. 기존 큐 종류·큐 인자·데이터 볼륨을 보존합니다.
3. API 결과 큐에 대한 복구가 필요할 때만 `broker-recovery.json`을 가져옵니다. 계정은 API 결과 실패 큐를 읽고 결과 큐와 해당 실패 큐로만 발행할 수 있습니다. 추출 런타임 계정은 이 경로로 발행할 수 없습니다.
4. 새 추출 이미지의 Python 런타임을 운영 브로커의 내부 Docker 네트워크에서 일회성 컨테이너로 실행합니다. `--env-file`로 비공개 `recovery.env`를 넘기고 `python -m mujuthaek_platform.recovery`로 대기 건수를 확인합니다. 실제 이동에는 `--apply --limit 10`을 붙입니다.
5. 작업을 마치면 RabbitMQ에서 `mujuthaek-api-recovery` 계정을 삭제합니다. 다음 복구에서는 새 임시 자격증명을 생성합니다. 일반 서비스 정의에는 이 임시 계정을 합치지 않습니다.

추출 입력은 해당 워커의 `python -m mujuthaek_extraction replay-dlq --queue notice --limit 10` 또는 `--queue policy`로 처리합니다. 운영 API 결과 재처리에는 위 임시 계정의 명령을 사용합니다. 제공자 잔액 부족이나 예산 상한으로 멈춘 메시지는 한도가 해소되었는지 먼저 확인합니다.

## 공고 처리 이력

운영 호스트에서 `sudo python3 broker_ledger.py trace --notice <notice-id>`를 실행합니다. 공개 이전 공고와 정정공고는 `--raw-post <raw-post-id>`로 조회할 수 있습니다. 수집 버전, Outbox 발행, 추출 시도, 검수 대기·결정, API 수신과 공개 버전이 시각순으로 표시됩니다. 원문·후보·검수 메모는 반환하지 않습니다. 조회 제한을 넘으면 `truncated`가 표시됩니다.

## 브로커 볼륨 손실

1. 발행기와 소비자를 제어할 수 있는 복구 시점과 손실 시간 범위를 기록합니다. 새 브로커에 기존 정의를 복원하고 대상 큐·바인딩을 먼저 확인합니다.
2. `sudo python3 broker_ledger.py plan --hours 24 --limit 500`으로 확정 발행과 소비 기록을 공고 수집·추출 결과 경로별로 대조합니다. `truncated`가 참이면 기간을 줄이고, 이전 구간에는 `--end`로 앞선 결과의 `window_start`를 넘겨 이어서 확인합니다.
3. `without_consumer_evidence`는 DB에 처리 근거가 없는 발행 ID입니다. 브로커가 살아 있다면 현재 큐에 남았거나 처리 중일 수 있습니다. `attempt_without_receipt`는 소비자가 이미 처리 기록을 남긴 건수입니다. 추출 실패나 자료 대기처럼 DB에 후속 처리가 남은 이벤트는 원본 메시지를 별도로 복구할지 결정하기 전에 그 기록을 확인합니다.
4. 정책 수집 메시지는 소비자가 저장한 수집 이벤트 키와 정책·버전 키로 대조합니다. 재처리 표시가 있는 메시지는 자기 이벤트 키로만 확인합니다. 처리 근거가 없는 메시지는 `needs_manual_policy_review`로 분류합니다. 수집 당시 꺼져 있던 분야나 지원하지 않는 분야는 소비자가 기록 없이 넘겼을 수 있습니다.
5. 운영자가 빈 큐와 중단 구간을 확인하고, 정책은 해당 분야의 처리 여부와 모델 비용까지 검토한 뒤 복구 대상을 확정합니다. 확정한 이벤트만 기존 ID로 다시 보내고 소비 기록을 확인합니다. 발행 전 Outbox에 남은 건은 일반 릴레이에 맡깁니다. 계획 명령은 읽기 전용입니다. 알림 경로와 DB 자체 손실은 이 명령의 범위 밖입니다.

## 실패 원인별 공고 추출 재시도

DB에 실패가 기록된 공고는 자료 대기, 일시 오류, 속도 제한 순서로 각각 기본 지연의 1배·2배·4배를 적용합니다. 같은 이벤트의 실패 횟수가 늘면 간격을 늘리며 최대 24시간과 기존 시도 횟수 상한을 적용합니다. 공급자 잔액·앱 예산·미분류 실패는 자동 재시도 대상에서 제외합니다. 원인을 해소한 뒤 `python -m mujuthaek_extraction retry --reason provider_credit --limit 10`처럼 사유와 대상을 제한해 재개합니다. 앱 예산은 `app_budget`, 미분류는 `other`입니다. 이 명령은 실제 추출을 시작하므로 모델 설정에 따라 비용이 발생할 수 있습니다.

## 로컬 장애 복구 계측

워크스페이스의 추출 Python 환경에서 `python backend/infra/deploy/personal/broker_recovery_drill.py --events 30`을 실행합니다. 미처리 1,857건을 모의하려면 `--events 3714`를 사용합니다. 스크립트가 루프백에만 연결한 임시 RabbitMQ를 만들고, 장애 탐지·설정 복원·발행과 소비 기록 대조·첫 이벤트 처리·적체 해소까지 단조 시계로 측정합니다. 합성 이벤트와 로컬 PC 측정값으로 운영 복구 시간을 산정하는 경우 부하와 인프라 차이를 고려합니다.
