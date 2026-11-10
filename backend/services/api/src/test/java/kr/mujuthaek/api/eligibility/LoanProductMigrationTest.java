package kr.mujuthaek.api.eligibility;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.eligibility.repository.LoanProductRepository;
import kr.mujuthaek.api.eligibility.rule.loan.LoanCatalog;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** 대출 상품 마이그레이션이 실제 PostgreSQL에 들어가고, 판정이 읽는 조건이 테스트가 쓰는 값(마이그레이션 파일)과 같은지 봐요. */
@SpringBootTest
@Import(TestcontainersConfiguration.class)
class LoanProductMigrationTest {

  @Autowired private LoanProductRepository repository;
  @Autowired private LoanCatalog catalog;

  @Test
  void everySeededRowIsReadBackTheSame() {
    MigrationLoanCatalog file = MigrationLoanCatalog.load();
    assertThat(repository.count()).isEqualTo(file.rows().size()).isEqualTo(11);
    for (String day :
        new String[] {"2025-12-31", "2026-01-01", "2026-10-18", "2026-10-19", "2026-10-21"}) {
      assertThat(catalog.asOf(LocalDate.parse(day)))
          .as("기준일 %s", day)
          .isEqualTo(file.asOf(LocalDate.parse(day)));
    }
  }
}
