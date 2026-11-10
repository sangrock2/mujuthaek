package kr.mujuthaek.api.eligibility.repository;

import java.util.UUID;
import kr.mujuthaek.api.eligibility.domain.SubscriptionDeposit;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SubscriptionDepositRepository extends JpaRepository<SubscriptionDeposit, UUID> {}
