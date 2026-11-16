package kr.mujuthaek.api.user.repository;

import jakarta.persistence.LockModeType;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.user.domain.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

public interface UserRepository extends JpaRepository<User, UUID> {

  /** 토큰 발급·회전·폐기를 같은 순서로 처리해, 로그아웃 뒤 새 토큰이 추가되지 않게 해요. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select u from User u where u.id = :id")
  Optional<User> lockById(UUID id);

  /** 회원 삭제. 소셜 계정·refresh token·탈퇴 티켓은 DB의 on delete cascade로 같이 지워져요. */
  @Modifying(clearAutomatically = true)
  @Query("delete from User u where u.id = :id")
  int deleteUser(UUID id);

  /** 가입 필수 동의를 했는지 (없는 회원이면 false) */
  @Query(
      value =
          "select exists (select 1 from account.users where id = :userId and terms_agreed_at is not null)",
      nativeQuery = true)
  boolean termsAgreed(UUID userId);
}
