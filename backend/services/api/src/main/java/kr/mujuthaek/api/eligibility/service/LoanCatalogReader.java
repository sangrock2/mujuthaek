package kr.mujuthaek.api.eligibility.service;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.domain.LoanProduct;
import kr.mujuthaek.api.eligibility.repository.LoanProductRepository;
import kr.mujuthaek.api.eligibility.rule.loan.LoanCatalog;
import kr.mujuthaek.api.eligibility.rule.loan.LoanTerms;
import org.springframework.stereotype.Component;

/** 대출 자격 판정(rule)에 대출 상품 조건을 DB에서 읽어 줘요. 표가 작아서(상품·시행일마다 한 행) 부를 때마다 모두 읽어요. */
@Component
class LoanCatalogReader implements LoanCatalog {

  private final LoanProductRepository repository;

  LoanCatalogReader(LoanProductRepository repository) {
    this.repository = repository;
  }

  @Override
  public List<LoanTerms> asOf(LocalDate day) {
    return LoanCatalog.latest(
        repository.findAll().stream().map(LoanProduct::toTerms).toList(), day);
  }
}
