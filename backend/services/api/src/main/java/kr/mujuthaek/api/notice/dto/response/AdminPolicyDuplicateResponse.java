package kr.mujuthaek.api.notice.dto.response;

import java.time.Instant;
import java.util.List;
import kr.mujuthaek.api.notice.repository.PolicyDuplicateRepository;

/**
 * 관리자 「중복 의심」 목록 (GET /api/admin/policy-duplicates). later가 나중에 들어온 사업, earlier가 먼저 있던 사업이에요.
 *
 * @param items 그 상태의 후보 (최근 순)
 * @param counts 상태별 건수 (갈래 숫자)
 */
public record AdminPolicyDuplicateResponse(List<Item> items, Counts counts) {

  /**
   * @param reason 같다고 본 근거 (SAME_TITLE_REGION: 같은 분야 · 같은 제목(띄어쓰기·기호 무시) · 같은 지역)
   * @param status PENDING · KEPT_BOTH · HIDDEN
   * @param decidedBy 처리한 관리자 ID
   */
  public record Item(
      Side later,
      Side earlier,
      String reason,
      String status,
      Instant createdAt,
      Instant decidedAt,
      String decidedBy) {

    public static Item of(PolicyDuplicateRepository.CandidateRow r) {
      return new Item(
          Side.of(r.later()),
          Side.of(r.earlier()),
          r.reason(),
          r.status(),
          r.createdAt(),
          r.decidedAt(),
          r.decidedBy());
    }
  }

  /**
   * 비교할 사업 하나.
   *
   * @param field STARTUP_SUPPORT · SPACE_RECRUITMENT
   * @param regionCodes 시군구 5자리, 빈 목록은 전국
   * @param createdAt 처음 받은 때
   * @param hidden 숨긴 사업인지
   */
  public record Side(
      java.util.UUID id,
      String field,
      String title,
      String organization,
      java.time.LocalDate applyStart,
      java.time.LocalDate applyEnd,
      List<String> regionCodes,
      String detailUrl,
      Instant createdAt,
      boolean hidden) {

    static Side of(PolicyDuplicateRepository.Side s) {
      return new Side(
          s.rawPolicyId(),
          s.field(),
          s.title(),
          s.organization(),
          s.applyStart(),
          s.applyEnd(),
          s.regionCodes(),
          s.detailUrl(),
          s.createdAt(),
          s.hidden());
    }
  }

  public record Counts(int pending, int keptBoth, int hidden) {}
}
