package kr.mujuthaek.api.eligibility.model;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/**
 * 목록 판정 후보 공고 하나 (notice가 줘요. 창업지원은 지원사업). 판정 틀과, 결과(MatchResult)에 그대로 옮길 공고 정보예요.
 *
 * @param policy 정책이면 true (사업공간 모집 정책, 창업지원 사업). 공고 상세 API로 찾을 수 없어 화면은 detailUrl로 보내요
 * @param regionCodes 공고 지역 법정동코드 10자리 (notice가 준 그대로). 판정에는 쓰지 않고 결과에 옮겨서 프론트가 지역으로 걸러요. 전국 공고는 빈
 *     목록, 지역을 모르면 null (빈 목록으로 바꾸면 모든 지역에 맞는 전국 공고처럼 보여서 null 그대로 둬요)
 * @param frame 판정 틀 (housing-judgment.v1 등). 아직 가공 전이면 null
 * @param detailUrl 원문 주소 (공고는 기관 원문, 정책은 수집한 원문). 모르면 null
 */
public record NoticeCandidate(
    UUID noticeId,
    boolean policy,
    int version,
    String title,
    LocalDate applyStart,
    LocalDate applyEnd,
    List<String> regionCodes,
    JsonNode frame,
    String detailUrl) {

  public NoticeCandidate {
    regionCodes = regionCodes == null ? null : List.copyOf(regionCodes);
  }
}
