// 백엔드 공고 코드 값 → 화면 문구 (목록 · 홈 · 상세가 같이 써요)

export const providerLabel: Record<string, string> = { APPLYHOME: "청약홈", MYHOME: "마이홈" };

export const providerName = (provider: string | null) =>
  provider ? (providerLabel[provider] ?? provider) : null;

export const noticeTypeLabel: Record<string, string> = {
  YOUTH_SAFE_HOUSING: "청년안심주택",
  PUBLIC_SUPPORT_PRIVATE_RENTAL: "공공지원민간임대",
  INTEGRATED_PUBLIC_RENTAL: "통합공공임대",
  PUBLIC_RENTAL: "공공임대",
  HAPPY_HOUSING: "행복주택",
  NATIONAL_RENTAL: "국민임대",
  PERMANENT_RENTAL: "영구임대",
  PURCHASE_RENTAL: "매입임대",
  JEONSE_RENTAL: "전세임대",
  LONG_TERM_JEONSE: "장기전세",
  PUBLIC_SALE: "공공분양",
  PRIVATE_SALE: "민영분양",
};

export const tagLabel: Record<string, string> = {
  STATION: "역세권",
  SCHOOL: "학세권",
  ELEMENTARY_NEAR: "초품아",
  PARK: "숲세권",
  CONVENIENCE: "편세권",
  CLINIC: "병세권",
};

export const targetGroupLabel: Record<string, string> = {
  YOUTH: "청년",
  NEWLYWED: "신혼부부",
  UNIVERSITY_STUDENT: "대학생",
  JOB_SEEKER: "취업준비생",
  ELDERLY: "고령자",
  MULTI_CHILD: "다자녀",
};

/** 준비할 돈을 계산하지 못한 이유 (prepareCostNote) */
export const prepareNoteLabel: Record<string, string> = {
  ASSET_UNKNOWN: "자산 조건 확인 필요",
  INCOME_UNKNOWN: "소득 조건 확인 필요",
  SCORE_UNKNOWN: "청약 가점 확인 필요",
  PRICE_NOT_ANNOUNCED: "공고에 금액이 아직 없어요",
  NO_ELIGIBLE_TYPE: "신청할 수 있는 주택형이 없어요",
};
