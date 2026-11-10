package kr.mujuthaek.api.eligibility.model;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.rule.Eligibility;

/**
 * 목록 판정 결과: 지원 가능·확인 필요 공고만 (지원 불가는 빠져요). 지원 가능 → 확인 필요 순이에요. 지원 가능 안에서는 내 순위 순(1순위 → 2순위 → … → 순위
 * 없음), 그다음 마감 빠른 순이에요. 저장하지 않아요.
 *
 * @param counts 상태별 공고 수 (홈 요약용)
 */
public record MatchResult(String field, Counts counts, List<Item> items) {

  public MatchResult {
    items = List.copyOf(items);
  }

  /**
   * @param notReady 판정 틀이 아직 없어 확인 필요인 공고 수 (checkNeeded에 포함)
   */
  public record Counts(int eligible, int needsInput, int notReady) {}

  /**
   * @param policy 정책이면 true (사업공간 모집 정책, 창업지원 사업). 공고 상세 API로 찾을 수 없으니 화면은 detailUrl(원문)로 보내요
   * @param detailUrl 원문 주소 (공고는 기관 원문, 정책은 수집한 원문). 모르면 null
   * @param regionCodes 공고 지역 법정동코드 10자리. 뒤가 0으로 채워진 단계는 그 지역 전체예요 (1100000000 = 서울 전체, 1168000000 =
   *     서울 강남구 전체). 프론트는 코드의 시군구 자리(3~5번째)가 000이면 시도 2자리만, 아니면 시군구 5자리까지 사용자가 고른 지역과 비교해서 걸러요. 전국
   *     공고는 빈 목록, 지역을 모르는 공고는 null (전국 공고와 달라요)
   * @param status ELIGIBLE 지원 가능 / NEEDS_INPUT 조건 확인 필요
   * @param rank 내 순위: 지원 가능일 때 충족한 대상군 중 가장 앞 신청 순위 (1이 가장 앞). 순위가 없는 공고·확인 필요면 null
   * @param reason 판정 틀이 없어 확인 필요면 CONDITIONS_NOT_READY, 아니면 null
   * @param groups 지원 가능이면 충족한 대상군, 확인 필요면 될 수도 있는 대상군 (이름)
   * @param missingInputs 확인 필요일 때 넣으면 결과가 정해질 수 있는 입력
   */
  public record Item(
      UUID noticeId,
      boolean policy,
      int version,
      String title,
      String detailUrl,
      List<String> regionCodes,
      LocalDate applyStart,
      LocalDate applyEnd,
      Eligibility status,
      Integer rank,
      String reason,
      List<String> groups,
      List<MissingInput> missingInputs) {}
}
