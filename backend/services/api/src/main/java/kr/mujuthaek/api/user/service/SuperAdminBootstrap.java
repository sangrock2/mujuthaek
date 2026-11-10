package kr.mujuthaek.api.user.service;

import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Component;

/**
 * 처음 최상위 관리자 지정. 최상위는 화면에서 만들 수 없어서, 배포 뒤 관리자로 쓸 계정으로 가입하고 그 회원 ID를 {@code
 * ADMIN_BOOTSTRAP_USER_ID}에 넣어 서버를 다시 띄우면 그 회원이 최상위가 돼요. 최상위가 이미 있으면 아무것도 안 해서 값을 그대로 둬도 괜찮아요. 처음
 * 가입한 사람을 자동으로 올리지 않아요 (배포 직후 아무나 먼저 가입하면 최상위가 되니까요).
 */
@Component
class SuperAdminBootstrap implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(SuperAdminBootstrap.class);

  private final AdminUserService admins;
  private final String userId;

  SuperAdminBootstrap(
      AdminUserService admins, @Value("${app.admin.bootstrap-user-id:}") String userId) {
    this.admins = admins;
    this.userId = userId;
  }

  @Override
  public void run(ApplicationArguments args) {
    if (userId == null || userId.isBlank()) {
      return;
    }
    UUID id;
    try {
      id = UUID.fromString(userId.strip());
    } catch (IllegalArgumentException e) {
      log.warn("ADMIN_BOOTSTRAP_USER_ID가 회원 ID 형식이 아니에요: {}", userId);
      return;
    }
    try {
      admins.bootstrapSuper(id);
    } catch (DataIntegrityViolationException e) {
      // 서버 여러 대가 동시에 떠도 최상위는 DB가 한 명만 받아요
      log.info("다른 서버가 먼저 최상위를 지정했어요: user={}", id);
    }
  }
}
