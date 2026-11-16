package kr.mujuthaek.notification.delivery.push;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

/** VAPID 개인키가 toString(로그·설정 오류)에 나오지 않아요 (2026-11-16 보안 감사 4장). */
class PushPropertiesTest {

  private static final String PRIVATE_PART = "private-part-for-test";

  @Test
  void toStringHidesThePrivateKey() {
    var props =
        new PushProperties(
            "webpush",
            "public-part",
            PRIVATE_PART,
            "mailto:a@b.c",
            List.of("fcm.googleapis.com"),
            Duration.ofSeconds(5));

    assertThat(props.toString())
        .doesNotContain(PRIVATE_PART)
        .contains("vapidPrivateKey=***")
        .contains("public-part");
  }

  @Test
  void toStringSaysWhenThereIsNoPrivateKey() {
    var props =
        new PushProperties(
            "log", "", "", "mailto:a@b.c", List.of("fcm.googleapis.com"), Duration.ofSeconds(5));

    assertThat(props.toString()).contains("vapidPrivateKey=(없음)");
  }
}
