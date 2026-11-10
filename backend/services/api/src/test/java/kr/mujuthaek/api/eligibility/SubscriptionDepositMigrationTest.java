package kr.mujuthaek.api.eligibility;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.eligibility.repository.SubscriptionDepositRepository;
import kr.mujuthaek.api.eligibility.rule.DepositRegion;
import kr.mujuthaek.api.eligibility.rule.SubscriptionDeposits;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** 예치기준금액 마이그레이션(4-08)이 실제 PostgreSQL에 들어가고, 판정이 읽는 값이 테스트가 쓰는 값(마이그레이션 파일)과 같은지 봐요. */
@SpringBootTest
@Import(TestcontainersConfiguration.class)
class SubscriptionDepositMigrationTest {

  @Autowired private SubscriptionDepositRepository repository;
  @Autowired private SubscriptionDeposits deposits;

  @Test
  void everySeededCellIsReadBackTheSame() {
    MigrationDeposits file = MigrationDeposits.load();
    assertThat(repository.count()).isEqualTo(file.rows().size()).isEqualTo(12);
    for (DepositRegion region : DepositRegion.values()) {
      for (String area : new String[] {"40", "85", "85.5", "102", "120", "135", "150"}) {
        for (LocalDate day :
            new LocalDate[] {LocalDate.of(2019, 1, 1), LocalDate.of(2026, 10, 16)}) {
          assertThat(deposits.find(day, region, new BigDecimal(area)))
              .as("%s %s㎡ %s", region, area, day)
              .isEqualTo(file.find(day, region, new BigDecimal(area)));
        }
      }
    }
  }
}
