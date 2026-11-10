package kr.mujuthaek.api.eligibility;

import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.eligibility.repository.BaseValueRepository;
import kr.mujuthaek.api.eligibility.rule.BaseValueKind;
import kr.mujuthaek.api.eligibility.rule.BaseValues;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** 기준값 마이그레이션이 실제 PostgreSQL에 들어가고, 판정이 읽는 값이 정답 케이스가 쓰는 값(마이그레이션 파일)과 같은지 봐요. */
@SpringBootTest
@Import(TestcontainersConfiguration.class)
class BaseValueMigrationTest {

  @Autowired private BaseValueRepository repository;
  @Autowired private BaseValues baseValues;

  @Test
  void everySeededRowIsReadBackTheSame() {
    MigrationBaseValues file = MigrationBaseValues.load();
    assertThat(repository.count()).isEqualTo(file.size()).isEqualTo(75);
    for (BaseValueKind kind : BaseValueKind.values()) {
      for (int year = 2024; year <= 2027; year++) {
        for (String program : new String[] {"", "영구임대", "국민임대", "행복주택(대학생)", "신혼희망타운(공공분양)"}) {
          for (int size = 0; size <= 10; size++) {
            assertThat(baseValues.find(kind, year, program, size))
                .as("%s %d %s %d인", kind, year, program, size)
                .isEqualTo(file.find(kind, year, program, size));
          }
        }
      }
    }
  }

  @Test
  void largeHouseholdsFollowTheOfficialFormula() {
    // 2026년 기준 중위소득 8인 = 7인 + 959,198원 (LH 통합공공임대 공고에 인쇄된 금액과 같아요)
    assertThat(baseValues.find(BaseValueKind.MEDIAN_INCOME, 2026, "", 8)).hasValue(10_474_348);
    // 2025년도 도시근로자 9인 = 8인 + 579,278원
    assertThat(baseValues.find(BaseValueKind.URBAN_WORKER_INCOME, 2025, "", 9))
        .hasValue(11_644_097);
    // 공공분양용 표는 1~3인이 같은 값
    assertThat(baseValues.find(BaseValueKind.URBAN_WORKER_AVERAGE_INCOME, 2025, "", 1))
        .hasValue(7_533_763);
    assertThat(baseValues.find(BaseValueKind.URBAN_WORKER_AVERAGE_INCOME, 2025, "", 4))
        .hasValue(8_802_202);
    assertThat(baseValues.find(BaseValueKind.CAR_VALUE, 2026, "행복주택(대학생)", 0)).isEmpty();
  }
}
