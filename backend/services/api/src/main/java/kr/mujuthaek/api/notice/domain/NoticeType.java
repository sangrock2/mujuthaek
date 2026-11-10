package kr.mujuthaek.api.notice.domain;

import java.util.Arrays;
import java.util.List;

/**
 * 공고 유형 코드 (API 설계 "이번에 정하는 코드"). 추출 결과의 원문 공급 유형(supplyType, 예: "매입임대")에서 정해요.
 *
 * <p>원문 표기가 여러 가지라 포함 여부로 찾고, 더 구체적인 이름을 먼저 봐요(통합공공임대가 공공임대보다 먼저, 공공지원민간임대가 민간임대보다 먼저). 못 찾으면
 * null이고 원문은 supply_type_text에 남아요.
 */
public enum NoticeType {
  // 주거
  YOUTH_SAFE_HOUSING("청년안심주택", "역세권청년주택", "역세권 청년주택"),
  PUBLIC_SUPPORT_PRIVATE_RENTAL("공공지원민간임대", "공공지원 민간임대"),
  INTEGRATED_PUBLIC_RENTAL("통합공공임대", "통합 공공임대"),
  // 5년·10년·50년 공공임대, 분납임대 (통합공공임대·공공지원민간임대 다음에 봐요)
  PUBLIC_RENTAL("공공임대", "분양전환", "분납임대"),
  HAPPY_HOUSING("행복주택"),
  NATIONAL_RENTAL("국민임대"),
  PERMANENT_RENTAL("영구임대"),
  PURCHASE_RENTAL("매입임대"),
  JEONSE_RENTAL("전세임대"),
  LONG_TERM_JEONSE("장기전세"),
  PUBLIC_SALE("공공분양", "신혼희망타운", "뉴홈"),
  PRIVATE_SALE("민영분양", "민간분양"),
  // 사업공간
  STARTUP_SPACE("창업", "입주기업"),
  SHOP_RENTAL("상가"),
  MEETING_ROOM("회의실", "대관");

  private final List<String> words;

  NoticeType(String... words) {
    this.words = List.of(words);
  }

  /** 원문 공급 유형에서 코드를 찾아요. 분야에 맞는 코드만 봐요 (사업공간 공고의 "상가"가 주거로 잡히지 않게). */
  public static NoticeType fromSupplyType(String supplyType, String field) {
    if (supplyType == null || supplyType.isBlank()) {
      return null;
    }
    String text = supplyType.replace(" ", "");
    return Arrays.stream(values())
        .filter(t -> t.isBusinessSpace() == "BUSINESS_SPACE".equals(field))
        .filter(t -> t.words.stream().anyMatch(w -> text.contains(w.replace(" ", ""))))
        .findFirst()
        .orElse(null);
  }

  public boolean isBusinessSpace() {
    return this == STARTUP_SPACE || this == SHOP_RENTAL || this == MEETING_ROOM;
  }
}
