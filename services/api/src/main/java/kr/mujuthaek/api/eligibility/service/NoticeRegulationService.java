package kr.mujuthaek.api.eligibility.service;

import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.region.CityDistricts;
import kr.mujuthaek.api.eligibility.dto.response.NoticeRegulationResponse;
import kr.mujuthaek.api.eligibility.repository.CriteriaAdminStore;
import kr.mujuthaek.api.eligibility.repository.CriteriaAdminStore.RegulatedArea;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 공고 지역의 규제지역 안내 (2026-10-25). 관리자가 넣은 규제지역 표(eligibility.regulated_areas)와 공고 지역을 맞춰 보고, 판정 화면에 보여
 * 줄 안내를 만들어요. 판정 값(지원 가능·불가)은 바꾸지 않아요: 판정 엔진에는 민영·공공 구분과 당첨 이력이 없고, 규제지역의 1순위 제한은 보통 공고문 조건으로 이미
 * 들어오기 때문이에요(사용자 결정).
 *
 * <p>주거 공고만 봐요. 확인 날짜는 접수 시작일(규제는 입주자모집공고 때 기준), 모르면 오늘이에요.
 */
@Service
public class NoticeRegulationService {

  static final Map<String, String> LABELS =
      Map.of(
          "SPECULATION_OVERHEATED", "투기과열지구",
          "ADJUSTMENT_TARGET", "조정대상지역",
          "SPECULATION", "투기지역");

  static final Map<String, String> GUIDANCE =
      Map.of(
          "SPECULATION_OVERHEATED",
          "투기과열지구예요. 민영주택 1순위는 보통 세대주여야 하고, 청약통장 가입 2년(국민주택은 24회 납입) 이상, 세대원 모두 최근 5년 안에 다른 주택에"
              + " 당첨된 적이 없어야 하며, 2주택 이상 가진 세대는 1순위가 될 수 없어요. 당첨되면 재당첨 제한이 있어요. 정확한 자격은 공고문을 확인하세요.",
          "ADJUSTMENT_TARGET",
          "조정대상지역이에요. 민영주택 1순위는 보통 세대주여야 하고, 청약통장 가입 2년(국민주택은 24회 납입) 이상, 세대원 모두 최근 5년 안에 다른 주택에"
              + " 당첨된 적이 없어야 하며, 2주택 이상 가진 세대는 1순위가 될 수 없어요. 정확한 자격은 공고문을 확인하세요.",
          "SPECULATION",
          "투기지역이에요. 주택담보대출 한도(LTV)가 낮아질 수 있어요. 대출 조건은 금융기관에 확인하세요.");

  private final NoticeQueryService notices;
  private final CriteriaAdminStore store;
  private final Clock clock;

  public NoticeRegulationService(
      NoticeQueryService notices, CriteriaAdminStore store, Clock clock) {
    this.notices = notices;
    this.store = store;
    this.clock = clock;
  }

  /** 없거나 숨김·공개 전 공고면 404 NOTICE_NOT_FOUND. */
  @Transactional(readOnly = true)
  public NoticeRegulationResponse forNotice(UUID noticeId) {
    NoticeSummary notice =
        notices
            .findSummary(noticeId)
            .orElseThrow(() -> new CustomException(ErrorCode.NOTICE_NOT_FOUND));
    LocalDate day = notice.applyStart() != null ? notice.applyStart() : LocalDate.now(clock);
    if (!"HOUSING".equals(notice.field())) {
      return new NoticeRegulationResponse(notice.noticeId(), day, false, List.of(), List.of());
    }
    List<NoticeRegulationResponse.Area> areas =
        match(notice.regionCodes(), store.regulatedAreas(day));
    return new NoticeRegulationResponse(
        notice.noticeId(), day, !areas.isEmpty(), areas, guidance(areas));
  }

  /**
   * 공고 지역(법정동 10자리)과 규제지역(시군구 5자리, 시도 전체는 xx000)을 맞춰요. 같은 시군구거나, 규제지역이 시도 전체면 그 시도의 모든 시군구가 걸려요.
   * 공고가 시도 전체(xx000…)면 그 시도 안 규제지역이 일부라도 있으면 걸리고 partial이에요. 전국 공고(빈 목록)는 걸리지 않아요.
   *
   * <p>일반구가 있는 시(수원시 41110 → 장안구 41111·권선구 41113 …)는 앞 4자리가 같아요. 규제지역이 시면 그 구 공고도 걸리고, 공고가 시인데
   * 규제지역이 그 시의 구 일부면 partial이에요(2026-10-25 검토: 예전엔 5자리가 같아야만 맞았음).
   */
  static List<NoticeRegulationResponse.Area> match(
      List<String> regionCodes, List<RegulatedArea> active) {
    List<NoticeRegulationResponse.Area> out = new ArrayList<>();
    Set<String> seen = new LinkedHashSet<>();
    for (String code : regionCodes == null ? List.<String>of() : regionCodes) {
      if (code == null || code.length() < 5) {
        continue;
      }
      String sigungu = code.substring(0, 5);
      boolean wholeSido = sigungu.endsWith("000");
      for (RegulatedArea area : active) {
        String target = area.regionCode();
        boolean sameSido = target.substring(0, 2).equals(sigungu.substring(0, 2));
        // 일반구가 있는 시는 공통 목록으로(재검토: 끝자리 0 모양으로 정해 증평군 공고가 영동군 규제지역에 걸렸음)
        boolean cityOfDistrict = CityDistricts.inCity(target, sigungu);
        boolean districtOfCity = CityDistricts.inCity(sigungu, target);
        boolean hit =
            target.equals(sigungu)
                || (target.endsWith("000") && sameSido)
                || (wholeSido && sameSido)
                || cityOfDistrict
                || districtOfCity;
        if (hit && seen.add(target + "/" + area.kind())) {
          boolean partial = (wholeSido && !target.endsWith("000")) || districtOfCity;
          out.add(
              new NoticeRegulationResponse.Area(
                  target,
                  area.kind(),
                  LABELS.getOrDefault(area.kind(), area.kind()),
                  partial,
                  area.scopeNote(),
                  area.validFrom(),
                  area.validUntil()));
        }
      }
    }
    return out;
  }

  static List<String> guidance(List<NoticeRegulationResponse.Area> areas) {
    Set<String> kinds = new LinkedHashSet<>();
    areas.forEach(a -> kinds.add(a.kind()));
    List<String> out = new ArrayList<>();
    for (String kind : List.of("SPECULATION_OVERHEATED", "ADJUSTMENT_TARGET", "SPECULATION")) {
      if (kinds.contains(kind)) {
        out.add(GUIDANCE.get(kind));
      }
    }
    if (areas.stream().anyMatch(NoticeRegulationResponse.Area::partial)) {
      out.add("공고 지역 중 일부 시군구만 규제지역이에요. 신청하려는 단지의 위치를 확인하세요.");
    }
    return out;
  }
}
