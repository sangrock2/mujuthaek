package kr.mujuthaek.api.eligibility.repository;

import java.util.UUID;
import kr.mujuthaek.api.eligibility.domain.LoanProduct;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LoanProductRepository extends JpaRepository<LoanProduct, UUID> {}
