package kr.mujuthaek.notification.delivery.email;

import java.time.Instant;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.UUID;
import kr.mujuthaek.notification.delivery.DeliveryException;
import kr.mujuthaek.notification.support.TimeConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * email.verification.requested: api가 만든 인증 코드를 메일로 바로 보내요. 회원이 화면에서 기다리고 있어서 발송 줄·묶음·조용한 시간 없이 보내요.
 *
 * <p>코드와 주소는 DB에 남기지 않아요. 실패해도 다시 시도하지 않고 로그만 남겨요. 회원이 화면에서 "다시 보내기"를 누르면 api가 새 코드로 다시 요청해요.
 */
@Component
public class VerificationMailer {

  private static final Logger log = LoggerFactory.getLogger(VerificationMailer.class);
  private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm");

  private final EmailSender sender;

  VerificationMailer(EmailSender sender) {
    this.sender = sender;
  }

  public void send(UUID userId, String email, String code, Instant expiresAt) {
    String until = TIME.format(ZonedDateTime.ofInstant(expiresAt, TimeConfig.SEOUL));
    String text =
        """
        무주택자들 알림 이메일 인증 코드예요.

        인증 코드: %s
        %s까지 화면에 입력해 주세요.

        직접 요청하지 않았다면 이 메일은 무시해 주세요.
        """
            .formatted(code, until);
    try {
      sender.send(new EmailMessage(email, "[무주택자들] 이메일 인증 코드 " + code, text));
      log.info("인증 메일 보냄: userId={}", userId);
    } catch (DeliveryException e) {
      log.warn("인증 메일 실패: userId={}, error={}", userId, e.code());
    }
  }
}
