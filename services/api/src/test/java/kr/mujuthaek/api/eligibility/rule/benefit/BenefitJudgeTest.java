package kr.mujuthaek.api.eligibility.rule.benefit;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.ApplicantBuilder;
import kr.mujuthaek.api.eligibility.rule.Bands;
import kr.mujuthaek.api.eligibility.rule.IncomeBenchmarks;
import kr.mujuthaek.api.eligibility.rule.Item;
import kr.mujuthaek.api.eligibility.rule.Overall;
import kr.mujuthaek.api.eligibility.rule.Status;
import kr.mujuthaek.api.eligibility.rule.benefit.BenefitJudge.Condition;
import org.junit.jupiter.api.Test;

/** 혜택 조건 판정 (benefit-condition-types.draft.md). 오늘은 2026-10-22. */
class BenefitJudgeTest {

  private static final LocalDate TODAY = LocalDate.of(2026, 10, 22);

  /** 2026년 기준중위소득 월액: 1인 250만, 2인 400만 */
  private static final IncomeBenchmarks MEDIAN =
      (standard, year, size) -> size == 1 ? 2_500_000L : size == 2 ? 4_000_000L : null;

  private static Condition c(String type, Map<String, Object> value, int group) {
    return new Condition(type, value, group, true, type + " 원문");
  }

  private static Status one(Condition c, Applicant a) {
    return BenefitJudge.judge(List.of(c), false, a, TODAY, MEDIAN).groups().getFirst().status();
  }

  private static Item item(Condition c, Applicant a) {
    return BenefitJudge.judge(List.of(c), false, a, TODAY, MEDIAN)
        .groups()
        .getFirst()
        .items()
        .getFirst();
  }

  private static ApplicantBuilder a() {
    return new ApplicantBuilder();
  }

  @Test
  void 나이는_출생_연월로_보고_생일_달이면_확인_필요() {
    Condition age = c("AGE", Map.of("min", 19, "max", 39), 1);
    assertThat(one(age, a().birthMonth(1997, 3).build())).isEqualTo(Status.MET);
    assertThat(one(age, a().birthMonth(1980, 3).build())).isEqualTo(Status.NOT_MET);
    assertThat(one(age, a().birthMonth(1986, 10).build())).isEqualTo(Status.UNKNOWN);
    assertThat(one(age, a().build())).isEqualTo(Status.UNKNOWN);
    assertThat(item(age, a().build()).needs()).containsExactly("applicant.birthDate");
  }

  @Test
  void 생년월일이_있으면_생일_달에도_나이가_정해진다() {
    Condition age = c("AGE", Map.of("min", 19, "max", 39), 1);
    // 오늘 2026-10-22: 1986-10-22생은 40세, 1986-10-23생은 아직 39세
    assertThat(one(age, a().birthDate(1986, 10, 22).build())).isEqualTo(Status.NOT_MET);
    assertThat(one(age, a().birthDate(1986, 10, 23).build())).isEqualTo(Status.MET);
  }

  @Test
  void 가구_소득은_받은_퍼센트_구간을_그대로_비교하고_걸치면_확인_필요() {
    Condition income = c("INCOME_MEDIAN_PCT", Map.of("max", 180, "basis", "HOUSEHOLD"), 1);
    assertThat(one(income, a().household(1).income("MEDIAN_INCOME", 90, 100).build()))
        .isEqualTo(Status.MET);
    assertThat(one(income, a().household(1).income("MEDIAN_INCOME", 180, 190).build()))
        .isEqualTo(Status.NOT_MET);
    assertThat(one(income, a().household(1).income("MEDIAN_INCOME", 170, 190).build()))
        .isEqualTo(Status.UNKNOWN);
  }

  @Test
  void 가구_소득_기준인데_본인_소득만_있으면_넘을_때만_불충족_아니면_원문_확인() {
    Condition pct = c("INCOME_MEDIAN_PCT", Map.of("max", 180, "basis", "HOUSEHOLD"), 1);
    Item under = item(pct, a().household(2).income("MEDIAN_INCOME", 90, 100).build());
    assertThat(under.status()).isEqualTo(Status.UNKNOWN);
    assertThat(under.reason()).isEqualTo(Bands.HOUSEHOLD_INCOME_UNKNOWN);
    assertThat(under.needs()).isEmpty();
    Item over = item(pct, a().household(2).income("MEDIAN_INCOME", 200, 210).build());
    assertThat(over.status()).isEqualTo(Status.NOT_MET);
    assertThat(over.reason()).isEqualTo(Bands.OWN_INCOME_OVER);

    // 연 5,000만 원 이하: 2인 90~100% = 월 360만~400만 → 연 4,320만~4,800만 → 가구는 몰라요
    Condition amount = c("INCOME_AMOUNT", Map.of("max", 5000, "basis", "HOUSEHOLD"), 1);
    assertThat(item(amount, a().household(2).income("MEDIAN_INCOME", 90, 100).build()).reason())
        .isEqualTo(Bands.HOUSEHOLD_INCOME_UNKNOWN);
    // 2인 110~120% = 연 5,280만~5,760만 → 본인만으로 넘어요
    assertThat(one(amount, a().household(2).income("MEDIAN_INCOME", 110, 120).build()))
        .isEqualTo(Status.NOT_MET);

    Item none = item(pct, a().household(2).build());
    assertThat(none.status()).isEqualTo(Status.UNKNOWN);
    assertThat(none.reason()).isEqualTo(Bands.NO_INCOME);
  }

  @Test
  void 본인_소득은_1인_기준으로_바꿔_비교한다() {
    // 2인 기준 50~60% = 월 200만~240만 → 1인 기준 80~96% → 100% 이하 충족
    Condition income = c("INCOME_MEDIAN_PCT", Map.of("max", 100, "basis", "PERSONAL"), 1);
    assertThat(one(income, a().household(2).income("MEDIAN_INCOME", 50, 60).build()))
        .isEqualTo(Status.MET);
    // 연 소득 2,500만 원 이하: 1인 90~100% = 월 225만~250만 → 연 2,700만~3,000만 → 불충족
    Condition amount = c("INCOME_AMOUNT", Map.of("max", 2500, "basis", "PERSONAL"), 1);
    assertThat(one(amount, a().household(1).income("MEDIAN_INCOME", 90, 100).build()))
        .isEqualTo(Status.NOT_MET);
  }

  @Test
  void 자산_무주택_혼인_자녀() {
    Condition asset = c("ASSET_AMOUNT", Map.of("max", 34500, "kind", "TOTAL"), 1);
    assertThat(one(asset, a().assets(0L, 200_000_000L).build())).isEqualTo(Status.MET);
    assertThat(one(asset, a().assets(345_000_000L, null).build())).isEqualTo(Status.NOT_MET);

    Condition homeless = c("HOMELESS_YEARS", Map.of("min", 1), 1);
    assertThat(one(homeless, a().homeOwner(false).homelessYears("1_3").build()))
        .isEqualTo(Status.MET);
    assertThat(one(homeless, a().homeOwner(true).build())).isEqualTo(Status.NOT_MET);

    Condition newlywed = c("MARITAL", Map.of("in", List.of("NEWLYWED")), 1);
    assertThat(one(newlywed, a().marital("MARRIED").married(2022, 5).build()))
        .isEqualTo(Status.MET);
    assertThat(one(newlywed, a().marital("MARRIED").married(2015, 5).build()))
        .isEqualTo(Status.NOT_MET);
    assertThat(one(newlywed, a().marital("SINGLE").build())).isEqualTo(Status.NOT_MET);

    Condition kids = c("CHILDREN", Map.of("minCount", 2), 1);
    assertThat(one(kids, a().children(1).build())).isEqualTo(Status.NOT_MET);
    assertThat(one(kids, a().children(2).build())).isEqualTo(Status.MET);
  }

  @Test
  void 거주_조건은_사는_곳이면_충족_아니면_이사_안내() {
    Condition residence = c("RESIDENCE", Map.of("regions", List.of("52730")), 1);
    assertThat(one(residence, a().region("52730").build())).isEqualTo(Status.MET);
    Item moved =
        BenefitJudge.judge(List.of(residence), false, a().region("11440").build(), TODAY, MEDIAN)
            .groups()
            .getFirst()
            .items()
            .getFirst();
    assertThat(moved.status()).isEqualTo(Status.UNKNOWN);
    assertThat(moved.reason()).isEqualTo("이 지역으로 이사하면 받을 수 있어요");
    // 2026-11-10 재검토: 일반구가 있는 시의 혜택은 그 구 주민도 사는 곳(장안구 주민에게 「이사하면」이 나왔음). 영동군 혜택은 증평군 주민 것이 아님
    Condition suwon = c("RESIDENCE", Map.of("regions", List.of("41110")), 1);
    assertThat(one(suwon, a().region("41111").build())).isEqualTo(Status.MET);
    Condition yeongdong = c("RESIDENCE", Map.of("regions", List.of("43740")), 1);
    assertThat(one(yeongdong, a().region("43745").build())).isEqualTo(Status.UNKNOWN);
  }

  @Test
  void 같은_그룹은_또는_다른_그룹은_그리고() {
    Applicant single = a().marital("SINGLE").birthMonth(1997, 3).build();
    var result =
        BenefitJudge.judge(
            List.of(
                c("AGE", Map.of("min", 19, "max", 39), 1),
                c("MARITAL", Map.of("in", List.of("MARRIED")), 2),
                c("HOUSEHOLD_TYPE", Map.of("in", List.of("SINGLE_PERSON")), 2)),
            false,
            a().marital("SINGLE").birthMonth(1997, 3).household(1).build(),
            TODAY,
            MEDIAN);
    assertThat(result.overall()).isEqualTo(Overall.ELIGIBLE);
    assertThat(result.summary().total()).isEqualTo(2);

    var no =
        BenefitJudge.judge(
            List.of(
                c("AGE", Map.of("min", 19, "max", 39), 1),
                c("MARITAL", Map.of("in", List.of("MARRIED")), 2)),
            false,
            single,
            TODAY,
            MEDIAN);
    assertThat(no.overall()).isEqualTo(Overall.INELIGIBLE);
  }

  @Test
  void 값_없는_조건과_입력_없는_조건은_확인_필요_중복_수혜는_안내만() {
    var result =
        BenefitJudge.judge(
            List.of(
                c("AGE", Map.of("min", 19, "max", 39), 1),
                new Condition("OTHER", Map.of(), 2, false, "공공임대 거주자 제외"),
                c("EMPLOYMENT", Map.of("in", List.of("EMPLOYED")), 3),
                new Condition("EXCLUSIVE", Map.of(), 4, false, "주거급여 수혜 중이면 제외")),
            false,
            a().birthMonth(1997, 3).build(),
            TODAY,
            MEDIAN);
    assertThat(result.overall()).isEqualTo(Overall.NEEDS_INPUT);
    assertThat(result.groups()).hasSize(3);
    assertThat(result.notes()).containsExactly("주거급여 수혜 중이면 제외");
  }

  @Test
  void 사람_확인_전_정책은_지원_가능을_넘지_않는다() {
    var result =
        BenefitJudge.judge(
            List.of(c("AGE", Map.of("min", 19, "max", 39), 1)),
            true,
            a().birthMonth(1997, 3).build(),
            TODAY,
            MEDIAN);
    assertThat(result.overall()).isEqualTo(Overall.NEEDS_INPUT);
    assertThat(result.reason()).isNotNull();
    assertThat(BenefitJudge.judge(List.of(), false, a().build(), TODAY, MEDIAN).overall())
        .isEqualTo(Overall.ELIGIBLE);
  }
}
