package kr.mujuthaek.notification.delivery.email;

/**
 * 메일 1통. {@code to}와 수신 해제 주소(서명이 들어 있어요)는 로그에 남기지 않아요(toString에서 가려요).
 *
 * @param oneClickUnsubscribeUrl 한 번 눌러 수신 해제하는 https 주소(RFC 8058). 있으면 {@code
 *     List-Unsubscribe}·{@code List-Unsubscribe-Post} 머리글을 붙여요. 없으면(인증 메일·로컬) null
 */
public record EmailMessage(String to, String subject, String text, String oneClickUnsubscribeUrl) {

  public EmailMessage(String to, String subject, String text) {
    this(to, subject, text, null);
  }

  @Override
  public String toString() {
    return "EmailMessage[to=***, subject="
        + subject
        + ", unsubscribe="
        + (oneClickUnsubscribeUrl == null ? "없음" : "***")
        + "]";
  }
}
