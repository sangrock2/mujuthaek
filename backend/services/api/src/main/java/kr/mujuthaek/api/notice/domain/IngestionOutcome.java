package kr.mujuthaek.api.notice.domain;

/** 받은 추출 결과를 어떻게 반영했는지 (extraction_results.outcome). */
public enum IngestionOutcome {
  /** 새 공고로 공개 */
  PUBLISHED,
  /** 공개 공고의 새 버전 */
  NEW_VERSION,
  /** 내용이 같아 새 버전을 만들지 않음 */
  NO_CHANGE,
  /** 공개된 자동 결과와 내용이 같은 승인본: 새 버전 없이 검수 상태만 승인으로 올림 (공고·후속 안내) */
  APPROVAL_RECORDED,
  /** 공개하지 않고 보관 (검수 대기, 상세 없음, 원래 공고가 아직 공개 전인 정정 공고) */
  HELD,
  /** 이미 반영한 원본보다 오래된 결과 */
  STALE,
  /** 같은 원본의 승인본이 이미 공개돼 있어 자동 결과로 바꾸지 않음 */
  KEPT_APPROVED,
  /** 같은 공고의 기준 출처가 아닌 출처의 새 버전: 출처 기록만 갱신하고 공고 내용은 바꾸지 않음 */
  KEPT_BASE_SOURCE,
  /** 정정 공고가 이미 반영돼 있어 원래 공고의 결과로 덮어쓰지 않음 */
  KEPT_CORRECTION,
  /** 후속 안내(서류 제출·발표 일정 등)를 원래 공고에 붙임 (새로 붙이거나 바뀐 내용으로 교체) */
  FOLLOW_UP_ATTACHED,
  /** 정책(창업지원·사업공간 모집) 판정 틀을 저장 (공고로 만들지 않음) */
  POLICY_JUDGMENT_SAVED,
  /** notice가 다루지 않는 분야 */
  UNSUPPORTED_FIELD,
  /** 이미 처리한 이벤트 (기록하지 않음) */
  DUPLICATE
}
