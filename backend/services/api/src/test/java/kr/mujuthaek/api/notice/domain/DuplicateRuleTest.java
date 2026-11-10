package kr.mujuthaek.api.notice.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.Set;
import kr.mujuthaek.api.notice.domain.DuplicateRule.Identity;
import org.junit.jupiter.api.Test;

class DuplicateRuleTest {

  private static final LocalDate DAY = LocalDate.of(2026, 10, 16);
  private static final Identity BASE =
      new Identity("서울특별시 서초구청", DAY, "서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고", Set.of("11650"));

  @Test
  void 기관_공고일_제목_지역이_모두_같으면_같은_공고다() {
    Identity sameWithSpacing =
        new Identity(
            "서울특별시  서초구청", DAY, "서초구 서리풀 청년아트타운 (잔여세대) 입주자 모집 공고", Set.of("11650", "11680"));

    assertThat(DuplicateRule.likelySame(BASE, sameWithSpacing)).isTrue();
  }

  @Test
  void 하나라도_다르면_같은_공고가_아니다() {
    assertThat(
            DuplicateRule.likelySame(BASE, new Identity("SH", DAY, BASE.title(), Set.of("11650"))))
        .isFalse();
    assertThat(
            DuplicateRule.likelySame(
                BASE,
                new Identity(
                    BASE.publisher(),
                    DAY.plusDays(DuplicateRule.WINDOW_DAYS + 1),
                    BASE.title(),
                    Set.of("11650"))))
        .isFalse();
    assertThat(
            DuplicateRule.likelySame(
                BASE, new Identity(BASE.publisher(), DAY, BASE.title() + " 2차", Set.of("11650"))))
        .isFalse();
    assertThat(
            DuplicateRule.likelySame(
                BASE, new Identity(BASE.publisher(), DAY, BASE.title(), Set.of("11680"))))
        .isFalse();
  }

  @Test
  void 공고일이나_기관을_모르면_후보로_보지_않는다() {
    assertThat(
            DuplicateRule.likelySame(
                new Identity(null, DAY, BASE.title(), Set.of()),
                new Identity(null, DAY, BASE.title(), Set.of())))
        .isFalse();
    assertThat(
            DuplicateRule.likelySame(
                BASE, new Identity(BASE.publisher(), null, BASE.title(), Set.of("11650"))))
        .isFalse();
  }

  @Test
  void 둘_다_지역을_모르면_지역은_보지_않는다() {
    Identity a = new Identity("LH", DAY, "행복주택 입주자 모집", Set.of());
    Identity b = new Identity("LH", DAY, "행복주택 입주자 모집", Set.of());

    assertThat(DuplicateRule.likelySame(a, b)).isTrue();
    assertThat(DuplicateRule.likelySame(a, new Identity("LH", DAY, a.title(), Set.of("11650"))))
        .isFalse();
  }

  @Test
  void 공고일이_한_달_안이면_같은_공고다() {
    assertThat(
            DuplicateRule.likelySame(
                BASE,
                new Identity(
                    BASE.publisher(),
                    DAY.plusDays(DuplicateRule.WINDOW_DAYS),
                    BASE.title(),
                    Set.of("11650"))))
        .isTrue();
  }

  @Test
  void 제목_형식이_달라도_단지_이름이_같으면_같은_공고다() {
    // 기관 게시판과 LH 마이홈은 제목 형식이 달라요(「부산 ○○ 행복주택」 / 「○○ 행복주택 입주자 모집공고」)
    Identity board =
        new Identity("부산도시공사", DAY, "명지 행복주택 입주자 모집공고", Set.of("26440"), Set.of("명지 행복주택"), "행복주택");
    Identity api =
        new Identity(
            "부산도시공사", DAY.plusDays(2), "부산 명지 행복주택", Set.of("26440"), Set.of("명지행복주택"), "행복주택");
    assertThat(DuplicateRule.likelySame(board, api)).isTrue();
    // 회차가 다르거나 공급 유형이 다르면 다른 공고
    Identity second =
        new Identity(
            "부산도시공사", DAY, "명지 행복주택 2차 입주자 모집공고", Set.of("26440"), Set.of("명지 행복주택"), "행복주택");
    assertThat(DuplicateRule.likelySame(board, second)).isFalse();
    Identity extra =
        new Identity(
            "부산도시공사", DAY, "명지 행복주택 추가 입주자 모집공고", Set.of("26440"), Set.of("명지 행복주택"), "행복주택");
    assertThat(DuplicateRule.likelySame(board, extra)).isFalse();
    Identity sale =
        new Identity("부산도시공사", DAY, "명지 행복주택 입주자 모집공고", Set.of("26440"), Set.of("명지 행복주택"), "분양주택");
    assertThat(DuplicateRule.likelySame(board, sale)).isFalse();
    // 단지 이름도 제목도 다르면 다른 공고
    Identity other =
        new Identity("부산도시공사", DAY, "다대 국민임대 모집공고", Set.of("26440"), Set.of("다대 국민임대"), "행복주택");
    assertThat(DuplicateRule.likelySame(board, other)).isFalse();
  }

  @Test
  void 기관_정식_명칭과_약칭은_같은_기관이다() {
    // 실측 2026-10-21: LH 청약 게시판과 마이홈의 같은 공고가 기관 표기만 달랐어요
    LocalDate day = LocalDate.of(2026, 9, 30);
    Identity board =
        new Identity(
            "LH 경남지역본부", day, "양산 삼성파크빌 국민임대 입주자 선착순 모집", Set.of("48330"), Set.of("삼성파크빌"), "국민임대");
    Identity myhome =
        new Identity(
            "한국토지주택공사 경남지역본부", day, board.title(), Set.of("48330"), Set.of("삼성파크빌"), "국민임대");
    Identity withoutPrefix =
        new Identity("경남지역본부", day, board.title(), Set.of("48330"), Set.of("삼성파크빌"), "국민임대");
    assertThat(DuplicateRule.likelySame(board, myhome)).isTrue();
    assertThat(DuplicateRule.likelySame(board, withoutPrefix)).isTrue();
    assertThat(
            DuplicateRule.likelySame(
                board,
                new Identity("SH", day, board.title(), Set.of("48330"), Set.of("삼성파크빌"), "국민임대")))
        .isFalse();
  }

  @Test
  void 단지_이름이_한쪽에_포함돼도_같은_단지다() {
    LocalDate day = LocalDate.of(2026, 8, 25);
    Identity a =
        new Identity(
            "광주전남지역본부",
            day,
            "빛가람LH3단지 잔여세대 일반매각 공고",
            Set.of("12170"),
            Set.of("광주전남혁신 빛가람LH3단지"),
            "잔여세대 일반매각");
    Identity b =
        new Identity(
            "광주전남지역본부",
            day.plusDays(3),
            "광주전남혁신 빛가람 LH3단지 잔여세대 일반매각",
            Set.of("12170"),
            Set.of("빛가람LH3단지"),
            "잔여세대 일반매각");
    assertThat(DuplicateRule.likelySame(a, b)).isTrue();
    // 실측: 같은 단지라도 공고일이 50일 차이 나는 재공고는 다른 공고
    assertThat(
            DuplicateRule.likelySame(
                a,
                new Identity(
                    b.publisher(),
                    day.plusDays(50),
                    b.title(),
                    b.sigunguCodes(),
                    b.complexNames(),
                    b.supplyType())))
        .isFalse();
  }
}
