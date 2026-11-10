package kr.mujuthaek.notification.delivery;

/** 묶음 종류(NotificationType.digest, 새 공고·새 정책)를 채널이 모아 보내는 간격. 같은 회원·같은 채널·같은 묶음 시각의 줄이 한 번에 나가요. */
public enum DigestCadence {
  /** 08:00·18:00 (이메일). 두 시각 모두 조용한 시간 밖이에요 */
  TWICE_A_DAY,
  /** 다음 정각 또는 30분 (웹 푸시). 폰이 연달아 울리지 않게 모으되 늦어도 30분이에요 */
  EVERY_30_MINUTES
}
