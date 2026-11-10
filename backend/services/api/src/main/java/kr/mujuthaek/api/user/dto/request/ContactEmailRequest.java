package kr.mujuthaek.api.user.dto.request;

import jakarta.validation.constraints.NotBlank;

/**
 * 연락용 이메일 등록·변경 본문 (PUT /api/users/me/email). 선택 항목이라 화면이 보여 준 동의 문구 버전을 같이 보내요.
 *
 * @param consentVersion 이메일 수집·이용 동의 문구 버전 (예: email-v1)
 */
public record ContactEmailRequest(@NotBlank String email, @NotBlank String consentVersion) {

  /** 주소는 로그·오류에 남기지 않아요 (toString 가림) */
  @Override
  public String toString() {
    return "ContactEmailRequest[consentVersion=" + consentVersion + "]";
  }
}
