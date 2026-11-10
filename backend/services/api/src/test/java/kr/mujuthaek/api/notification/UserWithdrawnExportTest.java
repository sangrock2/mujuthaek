package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.event.UserWithdrawn;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import kr.mujuthaek.api.user.service.WithdrawalService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 회원 탈퇴 → user.withdrawn (회원 삭제와 같은 트랜잭션으로 아웃박스에). 실제로 커밋해야 BEFORE_COMMIT이 불려서 테스트 트랜잭션을 쓰지 않아요.
 */
@SpringBootTest(properties = "app.outbox.scheduling-enabled=false")
@Import(TestcontainersConfiguration.class)
class UserWithdrawnExportTest {

  @Autowired WithdrawalService withdrawals;
  @Autowired SocialLoginService logins;
  @Autowired ApplicationEventPublisher events;
  @Autowired JdbcClient jdbc;
  @Autowired JsonMapper json;

  @BeforeEach
  void clear() {
    jdbc.sql("delete from common.outbox").update();
  }

  @Test
  void withdrawalIsExportedWithOnlyTheUserId() {
    String socialId = "export-" + UUID.randomUUID();
    LoginUser user = logins.login(new SocialProfile(SocialProvider.KAKAO, socialId, "닉네임"));

    withdrawals.withdraw(user.userId(), SocialProvider.KAKAO, socialId);

    List<JsonNode> sent = exported();
    assertThat(sent).hasSize(1);
    JsonNode envelope = sent.getFirst();
    assertThat(envelope.path("eventType").asString()).isEqualTo("user.withdrawn");
    assertThat(envelope.path("schemaVersion").asInt()).isEqualTo(1);
    assertThat(envelope.path("payload").propertyNames()).containsExactly("userId");
    assertThat(envelope.path("payload").path("userId").asString())
        .isEqualTo(user.userId().toString());
  }

  @Test
  void failedWithdrawalExportsNothing() {
    String socialId = "export-" + UUID.randomUUID();
    LoginUser user = logins.login(new SocialProfile(SocialProvider.KAKAO, socialId, "닉네임"));

    assertThatThrownBy(() -> withdrawals.withdraw(user.userId(), SocialProvider.KAKAO, "다른 계정"))
        .isInstanceOf(CustomException.class);

    assertThat(exported()).isEmpty();
  }

  @Test
  void eventOutsideATransactionIsNotExported() {
    events.publishEvent(new UserWithdrawn(UUID.randomUUID())); // 회원 삭제 없이 이벤트만

    assertThat(exported()).isEmpty();
  }

  private List<JsonNode> exported() {
    return jdbc
        .sql("select payload::text from common.outbox where event_type = 'user.withdrawn'")
        .query(String.class)
        .list()
        .stream()
        .map(json::readTree)
        .toList();
  }
}
