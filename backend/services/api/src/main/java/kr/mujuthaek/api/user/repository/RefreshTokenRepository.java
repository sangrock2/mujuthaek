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

  /** 잠금 전에 엔티티를 읽지 않아 회전 시각이 영속성 컨텍스트에 오래 남지 않게 해요. */
  @Query("select t.userId from RefreshToken t where t.tokenHash = :tokenHash")
  Optional<UUID> findUserIdByTokenHash(String tokenHash);

  @Query("select count(t) from RefreshToken t where t.userId = :userId and t.createdAt >= :since")
  long recentlyIssued(UUID userId, Instant since);

  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query("delete from RefreshToken t where t.userId = :userId and t.familyId = :familyId")
  int deleteFamily(UUID userId, UUID familyId);

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

  @Query(
      "select (count(t) > 0) from RefreshToken t where t.userId = :userId and t.familyId = :familyId and t.rotatedAt is null and t.expiresAt > :now")
  boolean activeFamily(UUID userId, UUID familyId, Instant now);

  /** 사용한 토큰의 해시도 원래 만료일까지 남겨 재사용을 감지해요. */
  @Modifying
  @Query("delete from RefreshToken t where t.expiresAt <= :now")
  int deleteExpired(Instant now);
}
