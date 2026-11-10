package kr.mujuthaek.notification.delivery;

/** 발송 채널 (deliveries.channel). 채널을 추가하면 마이그레이션의 check 조건도 같이 바꿔요. */
public enum Channel {
  EMAIL,
  PUSH
}
