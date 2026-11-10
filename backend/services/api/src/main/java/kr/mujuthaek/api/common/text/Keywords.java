package kr.mujuthaek.api.common.text;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

/**
 * 검색어. 띄어쓰기로 나눈 낱말이 <b>모두</b> 들어 있어야 맞아요(「마포 행복주택」 → 「마포」와 「행복주택」). 띄어쓰기와 대소문자는 보지 않아요(「행복 주택」도
 * 「행복주택」에 맞아요).
 */
public record Keywords(List<String> terms) {

  /** 낱말은 앞에서부터 이만큼만 봐요. */
  static final int MAX_TERMS = 5;

  static final int MAX_TERM_LENGTH = 30;

  public Keywords {
    terms = List.copyOf(terms);
  }

  /** 비었거나 공백뿐이면 낱말 없음(모두 맞음). */
  public static Keywords of(String keyword) {
    if (keyword == null || keyword.isBlank()) return new Keywords(List.of());
    return new Keywords(
        Arrays.stream(keyword.trim().split("\\s+"))
            .map(Keywords::normalize)
            .filter(t -> !t.isEmpty())
            .map(t -> t.length() > MAX_TERM_LENGTH ? t.substring(0, MAX_TERM_LENGTH) : t)
            .distinct()
            .limit(MAX_TERMS)
            .toList());
  }

  public boolean isEmpty() {
    return terms.isEmpty();
  }

  /** 낱말마다 texts 중 하나에라도 들어 있으면 맞아요. */
  public boolean matches(String... texts) {
    if (terms.isEmpty()) return true;
    String joined =
        normalize(String.join("\n", Arrays.stream(texts).filter(Objects::nonNull).toList()));
    return terms.stream().allMatch(joined::contains);
  }

  /** SQL like 패턴 (%낱말%). 낱말의 %·_·\는 글자 그대로 찾게 \로 막아요. 비교할 칸은 {@link #normalize}와 같게 공백을 빼고 소문자로. */
  public List<String> likePatterns() {
    return terms.stream()
        .map(t -> "%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        .toList();
  }

  static String normalize(String s) {
    return s.replaceAll("\\s+", "").toLowerCase(Locale.ROOT);
  }
}
