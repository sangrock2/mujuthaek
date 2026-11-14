package kr.mujuthaek.api.user.service;

/** 회원 모듈이 인증 메일을 요청하는 경계. 구현은 외부 발송 수단을 연결해요. */
public interface EmailVerificationSender {
  void sendEmailVerification(String address, String token);
}
