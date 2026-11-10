package kr.mujuthaek.api.user.repository;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.user.domain.RefreshToken;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

public interface RefreshTokenRepository extends JpaRepository<RefreshToken, UUID> {

  Optional<RefreshToken> findByTokenHash(String tokenHash);

  @Modifying
  @Query("delete from RefreshToken t where t.tokenHash = :tokenHash")
  int deleteByTokenHash(String tokenHash);

  @Modifying
  @Query("delete from RefreshToken t where t.userId = :userId")
  int deleteByUserId(UUID userId);

  /** 처음 연장할 때만 바꾼 시각을 적어요. 이미 적혀 있으면(다른 요청이 먼저 바꿈) 0줄. 같은 트랜잭션에서 다시 읽을 때 바뀐 시각이 보이게 앞뒤로 비워요. */
  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "update RefreshToken t set t.rotatedAt = :now where t.tokenHash = :tokenHash and t.rotatedAt is null")
  int markRotated(String tokenHash, Instant now);

  /** 만료된 값과, 바꾼 지 rotatedBefore보다 오래돼 더는 받지 않는 값을 지워요. */
  @Modifying
  @Query("delete from RefreshToken t where t.expiresAt <= :now or t.rotatedAt <= :rotatedBefore")
  int deleteExpired(Instant now, Instant rotatedBefore);
}
