package kr.mujuthaek.api.eligibility.dto.response;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/**
 * 공고 지역의 규제지역 안내. 판정 값은 바꾸지 않고 판정 화면에 함께 보여 줄 안내예요(2026-10-25 사용자 결정).
 *
 * @param noticeId 공고 ID
 * @param referenceDate 확인한 날짜 (접수 시작일, 모르면 오늘)
 * @param regulated 공고 지역(의 일부)이 그날 규제지역이면 true
 * @param areas 걸린 규제지역 (관리자가 넣은 지정·해제 기록 기준)
 * @param guidance 안내 문장 (규제 종류마다 하나, 공고문 확인 권유 포함)
 */
public record NoticeRegulationResponse(
    UUID noticeId,
    LocalDate referenceDate,
    boolean regulated,
    List<Area> areas,
    List<String> guidance) {

  /**
   * 걸린 규제지역 하나.
   *
   * @param regionCode 시군구 5자리 (시도 전체면 xx000)
   * @param kind SPECULATION_OVERHEATED 투기과열지구 · ADJUSTMENT_TARGET 조정대상지역 · SPECULATION 투기지역
   * @param kindLabel 한글 이름
   * @param partial 공고는 시도 전체인데 그 안의 일부 시군구만 규제지역이면 true
   * @param scopeNote 일부 지역만이면 그 설명 (예: 일부 동 제외)
   */
  public record Area(
      String regionCode,
      String kind,
      String kindLabel,
      boolean partial,
      String scopeNote,
      LocalDate validFrom,
      LocalDate validUntil) {}
}
