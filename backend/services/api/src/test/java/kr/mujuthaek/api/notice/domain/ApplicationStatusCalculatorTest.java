package kr.mujuthaek.api.notice.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator.Result;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator.Window;
import org.junit.jupiter.api.Test;

class ApplicationStatusCalculatorTest {

  private static final LocalDate OCT_20 = LocalDate.of(2026, 10, 20);
  private static final LocalDate OCT_21 = LocalDate.of(2026, 10, 21);
  private static final LocalDate OCT_25 = LocalDate.of(2026, 10, 25);
  private static final LocalDate OCT_26 = LocalDate.of(2026, 10, 26);

  private static final List<Window> TWO_ROUNDS =
      List.of(new Window(OCT_20, OCT_21), new Window(OCT_25, OCT_26));

  private static Result at(List<Window> windows, LocalDate today) {
    return ApplicationStatusCalculator.calculate(windows, false, today);
  }

  @Test
  void 시작_전이면_UPCOMING이고_시작일_0시에_다시_계산한다() {
    Result result = at(TWO_ROUNDS, OCT_20.minusDays(1));

    assertThat(result.status()).isEqualTo(NoticeStatus.UPCOMING);
    assertThat(result.nextCheckAt())
        .isEqualTo(OCT_20.atStartOfDay(ApplicationStatusCalculator.KOREA).toInstant());
  }

  @Test
  void 시작일과_마감일_당일은_접수_중이다() {
    assertThat(at(TWO_ROUNDS, OCT_20).status()).isEqualTo(NoticeStatus.APPLYING);
    assertThat(at(TWO_ROUNDS, OCT_21).status()).isEqualTo(NoticeStatus.APPLYING);
  }

  @Test
  void 접수_기간_사이는_다음_기간이_남아_UPCOMING이다() {
    Result result = at(TWO_ROUNDS, LocalDate.of(2026, 10, 23));

    assertThat(result.status()).isEqualTo(NoticeStatus.UPCOMING);
    assertThat(result.nextCheckAt())
        .isEqualTo(OCT_25.atStartOfDay(ApplicationStatusCalculator.KOREA).toInstant());
  }

  @Test
  void 모든_기간이_끝나면_CLOSED이고_다시_계산하지_않는다() {
    Result result = at(TWO_ROUNDS, OCT_26.plusDays(1));

    assertThat(result.status()).isEqualTo(NoticeStatus.CLOSED);
    assertThat(result.nextCheckAt()).isNull();
  }

  @Test
  void 끝난_기간과_날짜_미정_기간이_함께_있으면_마감으로_단정하지_않는다() {
    List<Window> windows = List.of(new Window(OCT_20, OCT_21), new Window(null, null));

    assertThat(at(windows, OCT_26).status()).isEqualTo(NoticeStatus.UNKNOWN);
    assertThat(at(windows, OCT_20).status()).isEqualTo(NoticeStatus.APPLYING); // 아는 기간이 열려 있으면 접수 중
  }

  @Test
  void 마감일이_없다는_이유만으로_상시_모집이_아니다() {
    List<Window> noEnd = List.of(new Window(OCT_20, null));

    assertThat(at(noEnd, OCT_21).status()).isEqualTo(NoticeStatus.UNKNOWN);
    assertThat(ApplicationStatusCalculator.calculate(noEnd, true, OCT_21).status())
        .isEqualTo(NoticeStatus.ALWAYS);
  }

  @Test
  void 일정이_없으면_상시_모집_명시일_때만_ROLLING() {
    assertThat(at(List.of(), OCT_20).status()).isEqualTo(NoticeStatus.UNKNOWN);
    assertThat(at(List.of(new Window(null, null)), OCT_20).status())
        .isEqualTo(NoticeStatus.UNKNOWN);
    assertThat(ApplicationStatusCalculator.calculate(List.of(), true, OCT_20).status())
        .isEqualTo(NoticeStatus.ALWAYS);
  }

  @Test
  void 마감이_아니던_공고가_마감될_때만_마감_알림_대상이다() {
    assertThat(ApplicationStatusCalculator.justClosed(NoticeStatus.APPLYING, NoticeStatus.CLOSED))
        .isTrue();
    assertThat(ApplicationStatusCalculator.justClosed(NoticeStatus.UPCOMING, NoticeStatus.CLOSED))
        .isTrue();
    assertThat(ApplicationStatusCalculator.justClosed(NoticeStatus.CLOSED, NoticeStatus.CLOSED))
        .isFalse();
    assertThat(ApplicationStatusCalculator.justClosed(null, NoticeStatus.CLOSED)).isFalse();
    assertThat(ApplicationStatusCalculator.justClosed(NoticeStatus.APPLYING, NoticeStatus.APPLYING))
        .isFalse();
  }

  @Test
  void 마감일은_가장_늦은_마감일이고_모르면_오늘이다() {
    assertThat(ApplicationStatusCalculator.closedOn(TWO_ROUNDS, OCT_26.plusDays(3)))
        .isEqualTo(OCT_26);
    assertThat(ApplicationStatusCalculator.closedOn(List.of(new Window(OCT_20, null)), OCT_25))
        .isEqualTo(OCT_25);
  }

  @Test
  void 시작을_모르는_기간이_마감_전이면_UNKNOWN_마감_후면_CLOSED() {
    List<Window> noStart = List.of(new Window(null, OCT_21));

    assertThat(at(noStart, OCT_20).status()).isEqualTo(NoticeStatus.UNKNOWN);
    assertThat(at(noStart, OCT_25).status()).isEqualTo(NoticeStatus.CLOSED);
  }
}
