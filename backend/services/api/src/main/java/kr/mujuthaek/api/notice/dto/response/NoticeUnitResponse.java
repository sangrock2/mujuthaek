package kr.mujuthaek.api.notice.dto.response;

import java.math.BigDecimal;
import java.util.List;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Evidence;

/**
 * 주택목록 한 호. 좌표는 area가 주소로 만들면 붙어요(아직 없음).
 *
 * @param siteName 단지·건물 이름 (단지별로 묶어 보여 줄 때)
 * @param depositWon 첫 가격 대상의 보증금 (가격 대상이 여럿이면 prices)
 * @param prices 가격 대상별 보증금·월임대료 (예: 「수급자 등」·「그 외」)
 * @param evidence 보증금·월임대료의 근거 원문
 */
public record NoticeUnitResponse(
    String id,
    String siteId,
    String siteName,
    String address,
    String unitLabel,
    String floor,
    String houseType,
    BigDecimal exclusiveM2,
    Long depositWon,
    Long rentWon,
    List<Price> prices,
    List<Evidence> evidence) {

  /**
   * 가격 대상 하나의 보증금·월임대료. 보류한 값은 비워요.
   *
   * @param targets 이 가격을 내는 대상 (비면 모든 신청자)
   */
  public record Price(List<String> targets, Long depositWon, Long rentWon) {}
}
