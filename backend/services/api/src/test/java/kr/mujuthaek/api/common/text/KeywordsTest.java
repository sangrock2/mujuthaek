package kr.mujuthaek.api.common.text;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class KeywordsTest {

  @Test
  void everyWordMustAppearIgnoringSpacesAndCase() {
    Keywords k = Keywords.of("  마포  행복 ");

    assertThat(k.terms()).containsExactly("마포", "행복");
    assertThat(k.matches("마포 행복주택", null)).isTrue();
    assertThat(k.matches("강남 행복주택", "마포구청")).isTrue(); // 낱말마다 어느 글에든 있으면 돼요
    assertThat(k.matches("강남 행복주택")).isFalse();
    assertThat(Keywords.of("행복주택").matches("행복 주택")).isTrue();
    assertThat(Keywords.of("LH").matches("lh 매입임대")).isTrue();
  }

  @Test
  void blankMatchesEverything() {
    assertThat(Keywords.of(null).isEmpty()).isTrue();
    assertThat(Keywords.of("   ").matches("아무 글")).isTrue();
  }

  @Test
  void likePatternsEscapeWildcards() {
    assertThat(Keywords.of("50%_할인").likePatterns()).containsExactly("%50\\%\\_할인%");
  }
}
