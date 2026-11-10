package kr.mujuthaek.api.notice.dto.response;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/**
 * 공고 상세 (API 설계 "상세 응답의 묶음"). 현재 공개 버전의 추출 결과에서 만들어요. 첨부는 기관 링크만 주고 파일은 주지 않아요.
 *
 * @param requiredDocuments 제출 서류 (서류 묶음 순서: 공통·해당자·본인 방문·배우자 대리·그 밖의 대리·묶음 없음). 보류한 서류는 빠져요
 * @param selectionRules 선정 방식 (순위·배점·추첨·선착순 등, 원문 순서). 보류한 항목은 빠져요
 * @param guidance 안내 (신청 방법·주의 사항·입주·거주·문의처, 원문 순서). 보류한 항목은 빠져요
 * @param heldItems 원문 확인 전까지 보여 주지 않는 항목 (일정·주택형·위치 등에서 뺐어요). 화면은 「확인 필요」로 알려요
 * @param areaSummaries 위치별 생활·상업 점수 (area가 계산한 공통 점수, 지금 위치로 계산한 것만)
 * @param followUps 원래 공고에 붙은 후속 안내 (서류 제출·당첨자 발표 등). 공고 버전과 따로 붙어요
 * @param hasUnits 호별 주택목록이 있는지 (없으면 화면이 주택목록·지도 섹션을 숨겨요)
 * @param reviewed 검수자가 확인한 버전인지
 */
public record NoticeDetailResponse(
    Header header,
    Summary summary,
    List<Schedule> schedules,
    List<Site> sites,
    List<UnitType> unitTypes,
    List<Condition> conditions,
    List<RequiredDocument> requiredDocuments,
    List<SelectionRule> selectionRules,
    List<Guidance> guidance,
    List<FileLink> files,
    List<HeldItem> heldItems,
    List<AreaSummary> areaSummaries,
    List<FollowUp> followUps,
    boolean hasUnits,
    int version,
    boolean reviewed,
    OffsetDateTime updatedAt) {

  public record Header(
      UUID id,
      String field,
      String title,
      String provider,
      String noticeType,
      String supplyTypeText,
      String status,
      LocalDate applyStart,
      LocalDate applyEnd,
      Integer dday,
      String regionCode,
      String regionName,
      LocalDate postedOn,
      String detailUrl,
      boolean needsCheck) {}

  /**
   * @param supplyTotal 모집 호수 (공고에 적힌 수, 없으면 주택형별 합)
   * @param applicationChannels 공고 전체 신청 방법 (ONLINE·ONSITE·EMAIL·MAIL·FAX, 신청 일정들의 방법을 합친 것)
   */
  public record Summary(
      String summaryText,
      List<String> targetGroups,
      Integer supplyTotal,
      BigDecimal exclusiveM2Min,
      BigDecimal exclusiveM2Max,
      List<String> applicationChannels) {}

  /**
   * @param kinds 일정 종류 (APPLICATION, VIEWING(주택 열람·방문 예약), DOCUMENT_SUBMISSION 등)
   * @param channels 신청·제출 방법 (ONLINE·ONSITE·EMAIL·MAIL·FAX). 이전 저장본의 자유 글자는 빠져요
   * @param places 방문 접수 장소 (원문에 그대로 있는 글자만, 모르는 칸은 null)
   * @param applicationEmail 이메일 접수 주소와 제목 형식 (없으면 null)
   * @param dailyHours 접수하는 날의 접수 시각 (HH:MM, 한국 시각)
   * @param breaks 접수하지 않는 시각 (점심시간 등)
   * @param excludedDays 접수하지 않는 요일·공휴일 (MON…SUN, HOLIDAY)
   * @param timeNote 시각에 붙은 조건 설명 (예: 마감일은 16시까지예요)
   * @param current 오늘이 이 일정 안이면 true (화면의 지금 단계 표시)
   * @param evidence 이 일정의 근거 원문
   */
  public record Schedule(
      String id,
      String label,
      List<String> kinds,
      String startsAt,
      String endsAt,
      String description,
      String applicationUrl,
      List<String> channels,
      List<Place> places,
      ApplicationEmail applicationEmail,
      List<TimeRange> dailyHours,
      List<TimeRange> breaks,
      List<String> excludedDays,
      String timeNote,
      boolean current,
      List<Evidence> evidence) {}

  /** 방문 접수 장소. 원문에 그대로 있는 글자만, 모르는 칸은 null이에요. */
  public record Place(String name, String address, String detail) {}

  /** 이메일 접수 주소와 원문이 정한 메일 제목 형식 (없으면 null). */
  public record ApplicationEmail(String address, String subjectFormat) {}

  /** 하루 안의 시각 구간 (HH:MM, 한국 시각). */
  public record TimeRange(String start, String end) {}

  /**
   * 제출 서류.
   *
   * @param group 서류 묶음: COMMON(공통), CONDITIONAL(해당자), DIRECT(본인 방문 신청), PROXY_SPOUSE(배우자 대리),
   *     PROXY_OTHER(그 밖의 대리), 원문이 나누지 않았으면 null
   * @param appliesTo 내는 사람 (원문 표현)
   * @param submissionTime 내는 때 (원문 표현)
   * @param copies 제출 부수 (원문에 있을 때만)
   * @param issuer 발급 기관 (원문에 있을 때만)
   * @param targetGroups 대상 계층 (비면 모든 계층)
   * @param evidence 이 서류의 근거 원문
   */
  public record RequiredDocument(
      String id,
      String name,
      String group,
      String appliesTo,
      String submissionTime,
      Integer copies,
      String issuer,
      String description,
      List<String> targetGroups,
      List<Evidence> evidence) {}

  /**
   * 선정 방식 한 줄.
   *
   * @param kind PRIORITY(순위), SCORING(배점), TIE_BREAK(동점 처리), LOTTERY(추첨), FIRST_COME(선착순),
   *     BIDDING(입찰), OTHER
   * @param priorityRank 순위 (순위 항목일 때)
   * @param points 배점표 한 행의 점수 (감점은 음수)
   * @param maxPoints 그 항목의 최고점
   * @param order 동점 처리 등의 적용 순서
   * @param targetGroups 대상 계층 (비면 모든 계층)
   * @param evidence 이 항목의 근거 원문
   */
  public record SelectionRule(
      String id,
      String kind,
      String description,
      String originalText,
      Integer priorityRank,
      BigDecimal points,
      BigDecimal maxPoints,
      Integer order,
      List<String> targetGroups,
      List<Evidence> evidence) {}

  /**
   * 안내 한 줄.
   *
   * @param kind APPLICATION_METHOD(신청 방법), CAUTION(주의 사항), MOVE_IN(입주), LIVING_NOTICE(거주),
   *     CONTACT(문의처), OTHER
   * @param phone 전화번호 (원문에 있을 때만)
   * @param url 안내 주소 (원문에 있을 때만)
   * @param evidence 이 안내의 근거 원문
   */
  public record Guidance(
      String id,
      String kind,
      String title,
      String description,
      String phone,
      String url,
      List<Evidence> evidence) {}

  /**
   * @param siteId area 위치 ID (GET /areas/sites/{siteId}). area가 아직 모르는 위치면 null
   * @param lat 좌표 (area가 못 찾았으면 null)
   * @param tags 세권 태그 (STATION, SCHOOL, ELEMENTARY_NEAR, PARK, CONVENIENCE, CLINIC)
   */
  public record Site(
      String id,
      String kind,
      String name,
      String address,
      String regionCode,
      UUID siteId,
      Double lat,
      Double lng,
      List<String> tags) {

    public Site withArea(UUID siteId, Double lat, Double lng, List<String> tags) {
      return new Site(id, kind, name, address, regionCode, siteId, lat, lng, tags);
    }
  }

  /** 같은 상세에 위치만 바꾼 것 (area 값을 붙일 때). */
  public NoticeDetailResponse withSites(List<Site> sites) {
    return new NoticeDetailResponse(
        header,
        summary,
        schedules,
        sites,
        unitTypes,
        conditions,
        requiredDocuments,
        selectionRules,
        guidance,
        files,
        heldItems,
        areaSummaries,
        followUps,
        hasUnits,
        version,
        reviewed,
        updatedAt);
  }

  /**
   * 공급 묶음별 주택형 줄(가격 대상이 여럿이면 대상마다 한 줄).
   *
   * @param targetGroups 이 줄의 가격 대상(가군·주거급여수급자 등), 없으면 공급 묶음의 대상
   * @param supplyCount 공급 호수. 같은 묶음의 줄이 여럿이면 첫 줄에만 있어요(합이 두 번 세지지 않게)
   * @param evidence 보여 주는 보증금·월임대료의 근거 원문
   * @param supplyGroupId 공급 묶음 ID (같은 묶음의 줄끼리 같아요)
   * @param siteName 단지·건물 이름 (모르면 null)
   * @param salePriceMinWon 분양가 가장 낮은 값 (층·안별로 여러 개일 때, 분양이 아니면 null)
   * @param salePriceMaxWon 분양가 가장 높은 값
   */
  public record UnitType(
      String houseType,
      List<String> targetGroups,
      BigDecimal exclusiveM2,
      Long depositWon,
      Long rentWon,
      Integer supplyCount,
      List<Evidence> evidence,
      String supplyGroupId,
      String siteName,
      Long salePriceMinWon,
      Long salePriceMaxWon) {}

  /**
   * 대상별 자격 조건과 근거 원문. 판정은 POST /eligibility/notices/{id}/evaluate로 해요.
   *
   * @param evidence 이 조건의 근거 원문 (원문 확인 전까지 보류한 조건은 비워요)
   */
  public record Condition(
      String id,
      String category,
      String target,
      List<String> targetGroups,
      String description,
      String originalText,
      boolean inReview,
      List<Evidence> evidence) {}

  /**
   * 값의 근거가 된 원문 인용. 모델 신뢰도는 계약에 없어서 주지 않아요(contracts/README.md).
   *
   * @param quote 원문 인용
   * @param page PDF의 실제 쪽 (1부터). 글자 범위 근거는 PDF 글자에서 쪽을 정한 경우만, 표 행 근거·쪽을 모르면 null
   * @param printedPage 그 쪽에 인쇄된 쪽 번호 (없으면 null)
   * @param documentName 근거 문서 이름 (첨부 파일 이름 또는 원문 글자 묶음 이름)
   */
  public record Evidence(String quote, Integer page, String printedPage, String documentName) {}

  public record FileLink(String name, String url) {}

  /**
   * 원문 확인 전까지 보여 주지 않는 항목.
   *
   * @param section 어느 섹션인지 (schedules, supplyGroups, locations, eligibility, notice …)
   * @param target 보류한 항목의 위치 (JSON Pointer, 예: /schedules/2)
   * @param description 확인이 필요한 이유
   */
  public record HeldItem(String section, String target, String description) {}

  /**
   * 위치 하나의 생활·상업 점수.
   *
   * @param siteId 단지·건물 (sites[].id)
   * @param kind LIVING(생활) 또는 COMMERCIAL(상업)
   * @param score 0~100
   */
  public record AreaSummary(
      String siteId, String kind, BigDecimal score, OffsetDateTime calculatedAt) {}

  /** 후속 안내 글 하나와 그 일정. */
  public record FollowUp(
      String title, String detailUrl, LocalDate postedOn, List<Schedule> schedules) {}
}
