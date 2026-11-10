package kr.mujuthaek.notification.delivery.email;

import java.time.Duration;
import kr.mujuthaek.notification.delivery.DeliveryException;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sesv2.SesV2Client;
import software.amazon.awssdk.services.sesv2.model.AccountSuspendedException;
import software.amazon.awssdk.services.sesv2.model.Body;
import software.amazon.awssdk.services.sesv2.model.Content;
import software.amazon.awssdk.services.sesv2.model.Destination;
import software.amazon.awssdk.services.sesv2.model.EmailContent;
import software.amazon.awssdk.services.sesv2.model.MailFromDomainNotVerifiedException;
import software.amazon.awssdk.services.sesv2.model.Message;
import software.amazon.awssdk.services.sesv2.model.MessageRejectedException;
import software.amazon.awssdk.services.sesv2.model.SendEmailRequest;
import software.amazon.awssdk.services.sesv2.model.SendingPausedException;
import software.amazon.awssdk.services.sesv2.model.SesV2Exception;

/**
 * AWS SES로 보내요 (notification.mail.provider=ses). 키는 기본 자격 증명 순서(AWS_PROFILE, 환경 변수, 서버 역할)로 읽어요.
 *
 * <p>SES 초당 한도를 넘지 않게 보내는 사이 간격을 둬요. 주소 문제(MessageRejected)는 다시 보내도 같아서 바로 실패로, 나머지는 다시 보내요.
 */
@Component
@ConditionalOnProperty(name = "notification.mail.provider", havingValue = "ses")
class SesEmailSender implements EmailSender, AutoCloseable {

  private static final String UTF_8 = "UTF-8";

  private final SesV2Client ses;
  private final String from;
  private final long intervalNanos;
  private long nextSendAt = System.nanoTime();

  SesEmailSender(MailProperties properties) {
    this.ses = SesV2Client.builder().region(Region.of(properties.ses().region())).build();
    this.from = properties.from();
    this.intervalNanos =
        Duration.ofSeconds(1).toNanos() / Math.max(1, properties.ses().maxPerSecond());
  }

  @Override
  public String send(EmailMessage message) throws DeliveryException {
    throttle();
    SendEmailRequest request =
        SendEmailRequest.builder()
            .fromEmailAddress(from)
            .destination(Destination.builder().toAddresses(message.to()).build())
            .content(
                EmailContent.builder()
                    .simple(
                        Message.builder()
                            .subject(text(message.subject()))
                            .body(Body.builder().text(text(message.text())).build())
                            .build())
                    .build())
            .build();
    try {
      return ses.sendEmail(request).messageId();
    } catch (MessageRejectedException | MailFromDomainNotVerifiedException e) {
      throw new DeliveryException("SES_" + code(e), true, e);
    } catch (AccountSuspendedException | SendingPausedException e) {
      throw new DeliveryException("SES_" + code(e), false, e); // 계정 문제: 풀리면 다시 보내요
    } catch (SesV2Exception e) {
      throw new DeliveryException("SES_" + code(e), false, e);
    } catch (SdkClientException e) {
      throw new DeliveryException("SES_CLIENT", false, e); // 네트워크·자격 증명
    }
  }

  private synchronized void throttle() {
    long wait = nextSendAt - System.nanoTime();
    if (wait > 0) {
      try {
        Thread.sleep(Duration.ofNanos(wait));
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
      }
    }
    nextSendAt = Math.max(nextSendAt, System.nanoTime()) + intervalNanos;
  }

  private static Content text(String value) {
    return Content.builder().data(value).charset(UTF_8).build();
  }

  private static String code(SesV2Exception e) {
    return e.awsErrorDetails() == null
        ? e.getClass().getSimpleName()
        : e.awsErrorDetails().errorCode();
  }

  @Override
  public void close() {
    ses.close();
  }
}
