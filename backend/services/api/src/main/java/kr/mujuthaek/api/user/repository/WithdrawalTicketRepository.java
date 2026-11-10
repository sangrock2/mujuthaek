package kr.mujuthaek.api.user.repository;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.user.domain.WithdrawalTicket;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

public interface WithdrawalTicketRepository extends JpaRepository<WithdrawalTicket, UUID> {

  Optional<WithdrawalTicket> findByTicketHash(String ticketHash);

  @Modifying
  @Query("delete from WithdrawalTicket t where t.ticketHash = :ticketHash")
  int deleteByTicketHash(String ticketHash);

  @Modifying
  @Query("delete from WithdrawalTicket t where t.userId = :userId")
  int deleteByUserId(UUID userId);

  @Modifying
  @Query("delete from WithdrawalTicket t where t.expiresAt <= :now")
  int deleteExpired(Instant now);
}
