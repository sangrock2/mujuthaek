package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.event.PolicyHidden;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.repository.FavoriteRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;

/** 관리자가 중복 정책 사업을 숨기면(PolicyHidden) 숨긴 사업에 둔 관심이 남은 사업으로 옮겨가요. */
@SpringBootTest
@Import(TestcontainersConfiguration.class)
class PolicyHiddenFavoriteTest {

  @Autowired SocialLoginService logins;
  @Autowired FavoriteRepository favorites;
  @Autowired ApplicationEventPublisher events;
  @Autowired JdbcClient jdbc;

  @Test
  void favoritesOfAHiddenDuplicatePolicyMoveToTheKeptOne() {
    // 2026-11-10 재검토: 숨긴 사업의 관심은 목록에 빈 줄로 남고, 남은 사업의 마감·정정 알림을 받지 못했음
    UUID hidden = UUID.randomUUID();
    UUID kept = UUID.randomUUID();
    UUID onlyHidden =
        logins.login(new SocialProfile(SocialProvider.KAKAO, "ph-1", "닉ph-1")).userId();
    UUID both = logins.login(new SocialProfile(SocialProvider.KAKAO, "ph-2", "닉ph-2")).userId();
    Instant now = Instant.now();
    favorites.add(onlyHidden, "SPACE_RECRUITMENT", hidden, now);
    favorites.add(both, "SPACE_RECRUITMENT", hidden, now);
    favorites.add(both, "SPACE_RECRUITMENT", kept, now);

    events.publishEvent(new PolicyHidden(hidden, kept)); // 숨김 트랜잭션 밖에서 보내면 바로 받아요

    assertThat(targets(onlyHidden)).containsExactly(kept);
    assertThat(targets(both)).containsExactly(kept); // 둘 다 뒀으면 숨긴 쪽 줄만 지움
  }

  private List<UUID> targets(UUID user) {
    return jdbc.sql("select target_id from account.favorites where user_id = :u")
        .param("u", user)
        .query(UUID.class)
        .list();
  }
}
