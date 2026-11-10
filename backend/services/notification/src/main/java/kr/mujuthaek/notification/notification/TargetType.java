package kr.mujuthaek.notification.notification;

/** 알림이 가리키는 대상이 들어 있는 api 테이블. 발송에는 쓰지 않고 요청이 계약에 맞는지 확인할 때만 봐요. */
public enum TargetType {
  NOTICE, // notices
  BENEFIT, // benefits
  STARTUP_SUPPORT, // notice.policy_judgments (창업지원 사업)
  SPACE_RECRUITMENT // notice.policy_judgments (사업공간 모집)
}
