package kr.mujuthaek.api.notice.domain;

import java.time.Instant;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * 같은 공고가 여러 출처에서 들어왔을 때 공고 내용을 대표할 기준 출처 고르기 (2-13, 사용자 결정 2026-10-21). 스프링·DB 없이 값만 보고 정해요.
 *
 * <ol>
 *   <li>공고문 PDF가 있는 출처
 *   <li>먼저 게시된 출처 (원래 공고 글의 게시일, 모르면 뒤로)
 *   <li>먼저 들어온 출처 (우리 쪽에 처음 반영된 시각)
 *   <li>지금 기준 출처 (위가 모두 같으면 기준을 바꾸지 않아요)
 *   <li>원래 공고 글 ID 순서 (항상 같은 결과가 나오게)
 * </ol>
 */
public final class BaseSource {

  private BaseSource() {}

  /** 출처 하나. root는 원래 공고 글(정정 공고는 가리키는 원래 글로 셈). */
  public record Candidate(UUID root, boolean hasPdf, LocalDate postedOn, Instant firstSeenAt) {}

  public static Optional<Candidate> choose(List<Candidate> candidates) {
    return choose(candidates, null);
  }

  /** current: 지금 기준 출처(없으면 null). */
  public static Optional<Candidate> choose(List<Candidate> candidates, UUID current) {
    Comparator<Candidate> order =
        Comparator.comparing((Candidate c) -> !c.hasPdf())
            .thenComparing(Candidate::postedOn, Comparator.nullsLast(Comparator.naturalOrder()))
            .thenComparing(Candidate::firstSeenAt, Comparator.nullsLast(Comparator.naturalOrder()))
            .thenComparing(c -> !c.root().equals(current))
            .thenComparing(Candidate::root);
    return candidates.stream().min(order);
  }
}
