// 화면용 예시 데이터 (디자인 WebBusiness · WebBizOnboarding · WebSpaceDetail · WebBizSupport와 모바일 짝). 실제 값은 API에서 받아요.
import type { ListingVerdict, Verdict } from "@/components/ui/Badge";

/* ---------- 사업 정보 ---------- */

export type BizStage = "pre" | "run";

export type BizProfile = {
  stage: BizStage;
  stageLabel: string;
  industry: string;
  staff: string;
  region: string;
};

export const bizProfile: BizProfile = {
  stage: "pre",
  stageLabel: "예비 창업",
  industry: "소프트웨어 개발",
  staff: "1인",
  region: "마포구",
};

/* ---------- 사업공간 홈 ---------- */

export type SpaceType = "startup" | "shop" | "room";

export type SpaceItem = {
  id: string;
  type: SpaceType;
  /** 판정이 없는 공간(회의실 대관 등)은 null */
  verdict: Verdict | null;
  org: string;
  title: string;
  info: string;
  tags: string[];
  money: string;
  due: string;
  /** 상세 화면 없이 원문으로 보내는 공간 (사업공간 모집 정책) */
  externalUrl?: string;
};

export type BusinessSummary = {
  /** newThisWeek: 실제 API는 아직 몰라서 없어요 */
  spaces: { count: number; closingSoon: number; newThisWeek?: number };
  /** maxAmount: 실제 API는 지원 금액을 몰라서 없어요 */
  support: { count: number; maxAmount?: string; needCheck: number };
  list: SpaceItem[];
};

export const businessSummary: BusinessSummary = {
  spaces: { count: 4, closingSoon: 1, newThisWeek: 2 },
  support: { count: 3, maxAmount: "1억 원", needCheck: 1 },
  list: [
    {
      id: "s1",
      type: "startup",
      verdict: "ok",
      org: "창업보육센터 · ○○대학교",
      title: "○○창업보육센터 입주기업 모집",
      info: "최대 2년 · 서류 · 발표 심사",
      tags: ["본점 이전 필요", "1인실 있음"],
      money: "관리비 월 15만 원",
      due: "D-14",
    },
    {
      id: "s2",
      type: "shop",
      verdict: "check",
      org: "LH 상가 · 입찰",
      title: "○○지구 단지 내 상가",
      info: "전용 33㎡ · 1층",
      tags: ["청년 우대", "소상공인 우대"],
      money: "예정 임대료 월 85만 원",
      due: "D-9",
    },
    {
      id: "s3",
      type: "startup",
      verdict: "ok",
      org: "청년창업센터 · ○○구",
      title: "○○구 청년창업센터 2기",
      info: "최대 1년 · 서류 심사",
      tags: ["1인 창업 가능", "역세권"],
      money: "입주비 없음",
      due: "D-21",
    },
    {
      id: "s4",
      type: "shop",
      verdict: "ok",
      org: "SH 상가 · 입찰",
      title: "○○ 단지 내 상가",
      info: "전용 26㎡ · 1층",
      tags: ["청년 우대"],
      money: "예정 임대료 월 62만 원",
      due: "D-30",
    },
    {
      id: "s5",
      type: "room",
      verdict: null,
      org: "공유누리 · 회의실",
      title: "○○구청 3층 회의실",
      info: "8명 · 빔프로젝터",
      tags: ["평일 저녁 가능"],
      money: "시간당 1만 원",
      due: "예약 가능",
    },
  ],
};

/* ---------- 사업 지원 ---------- */

export type SupportType = "fund" | "loan" | "tax";

/** 판정 배지 또는 판정이 아닌 상태(회색) */
export type SupportStatus = Verdict | "afterStart";

export type SupportItem = {
  id: string;
  type: SupportType;
  status: SupportStatus;
  title: string;
  org: string;
  /** 모바일에서 줄여 쓰는 기관명 */
  mOrg: string;
  body: string;
  note: string;
  /** 모바일은 내용 한 줄로 합쳐 보여줘요 */
  mBody: string;
  reason: string;
  mReason: string;
  /** 사업공간 홈 오른쪽 목록의 한 줄 설명 */
  summary: string;
  due: string;
  /** 상세 화면 (실제 API) */
  href?: string;
};

export type SupportList = {
  count: number;
  baseDate: string;
  items: SupportItem[];
  /** 사업장 소재지를 넣으면 판정할 수 있는 사업 수 */
  missingSiteCount?: number;
};

export const supportList: SupportList = {
  count: 3,
  baseDate: "10월 20일",
  missingSiteCount: 1,
  items: [
    {
      id: "f1",
      type: "fund",
      status: "ok",
      title: "예비창업 지원사업",
      org: "창업진흥원 · 공간 연결",
      mOrg: "창업진흥원 · 공간 연결",
      body: "최대 1억 원",
      note: "선정되면 창업 공간에 우선 입주",
      mBody: "최대 1억 원 · 선정되면 창업 공간 입주",
      reason: "예비 창업 · 나이 충족",
      mReason: "예비 창업 · 나이 충족",
      summary: "최대 1억 원 · 선정되면 창업 공간 입주",
      due: "D-18",
    },
    {
      id: "l1",
      type: "loan",
      status: "ok",
      title: "청년 창업 정책자금",
      org: "중소벤처기업진흥공단",
      mOrg: "중소벤처기업진흥공단",
      body: "한도 1억 원 · 고정금리 대출",
      note: "사업계획 평가 후 대출",
      mBody: "한도 1억 원 · 고정금리 대출",
      reason: "업력 · 나이 충족",
      mReason: "업력 · 나이 충족",
      summary: "한도 1억 원 · 낮은 고정금리 대출",
      due: "상시",
    },
    {
      id: "f2",
      type: "fund",
      status: "check",
      title: "○○구 청년 창업 지원금",
      org: "○○구청 · 공고 확인 필요",
      mOrg: "○○구청",
      body: "최대 500만 원",
      note: "임차료 · 마케팅비 사용",
      mBody: "최대 500만 원 · 임차료 · 마케팅비",
      reason: "사업장 소재지가 필요해요",
      mReason: "사업장 소재지가 필요해요",
      summary: "최대 500만 원 · 사업장 소재지가 필요해요",
      due: "11월 10일",
    },
    {
      id: "t1",
      type: "tax",
      status: "afterStart",
      title: "청년 창업 세액감면",
      org: "국세청 · 정보 제공",
      mOrg: "국세청 · 정보 제공",
      body: "소득세 · 법인세 50~100% 감면 · 5년",
      note: "감면율은 사업장 지역에 따라 달라요",
      mBody: "소득세 · 법인세 50~100% 감면 · 5년",
      reason: "사업자등록 후 신고할 때 신청",
      mReason: "감면율은 사업장 지역에 따라 달라요",
      summary: "소득세 · 법인세 50~100% 감면 · 5년",
      due: "-",
    },
  ],
};

/* ---------- 공간 상세 ---------- */

export type SpaceFact = { label: string; value: string; mValue: string };
export type SpaceCondition = { label: string; value: string; note?: string; mValue: string };
export type SpaceDoc = { name: string; note: string; mNote: string; ready: boolean };
export type SpaceStep = { step: number; title: string; when: string };
export type SpaceRule = {
  label: string;
  rule: string;
  mRule: string;
  met: boolean;
  /** 근거 원문 문장 (실제 API) */
  quote?: string;
  /** 불충족으로 정해짐 (실제 API) */
  notMet?: boolean;
  /** 확인 필요일 때 넣으면 정해지는 입력을 받는 화면. 없으면 원문 확인 (실제 API) */
  inputHref?: string;
  /** "다음 중 하나만 맞으면 돼요" 묶음의 길들 (실제 API) */
  options?: { label: string; met: boolean; notMet: boolean; rules: SpaceRule[] }[];
};

export type SpaceDetail = {
  id: string;
  /** 관심 등록·제보 대상 종류: 사업공간 공고(NOTICE) · 사업공간 모집 정책(SPACE_RECRUITMENT). 목업은 없음 */
  favoriteType?: "NOTICE" | "SPACE_RECRUITMENT";
  verdict: ListingVerdict;
  due: string;
  tag: string;
  title: string;
  kind: string;
  host: string;
  area: string;
  facts: SpaceFact[];
  conditions: SpaceCondition[];
  docs: SpaceDoc[];
  /** 지금 진행 중인 단계 번호 */
  currentStep: number;
  schedule: SpaceStep[];
  rules: SpaceRule[];
  /** 함께 받을 지원. 실제 API는 아직 없어요 */
  linkedSupport?: { id: string; title: string; desc: string; amount: string };
  /** 공고 원문 */
  sourceUrl?: string;
  /** 판정 틀이 아직 없어 자격을 판정하지 못함 (자격 조건 정리 중) */
  notReady?: boolean;
  /** 요약 아래 안내 (모집 정책: 입주 조건은 원문에서) */
  summaryNote?: string;
  /** 공고 안내: 출처 요약 · 기관 · 문의처 · 접수 방법 · 링크 (모집 정책 · 사업 지원, 실제 API) */
  about?: { summary?: string; rows: { label: string; value: string; href?: string }[] };
};

export const spaceDetails: SpaceDetail[] = [
  {
    id: "s1",
    verdict: "ok",
    due: "D-14",
    tag: "본점 이전 필요",
    title: "○○창업보육센터 입주기업 모집",
    kind: "창업보육센터",
    host: "○○대학교 산학협력단",
    area: "서울 마포구",
    facts: [
      { label: "선정 방식", value: "서류 · 발표 심사", mValue: "서류 · 발표" },
      { label: "모집", value: "10개 기업", mValue: "10개 기업" },
      { label: "접수 마감", value: "11월 3일", mValue: "11월 3일" },
      { label: "입주 공간", value: "1인실 ~ 4인실", mValue: "1인실 ~ 4인실" },
    ],
    conditions: [
      { label: "입주 기간", value: "최대 2년 · 1년마다 평가", mValue: "최대 2년" },
      { label: "본점 이전", value: "입주 후 3개월 안", mValue: "입주 후 3개월 안" },
      { label: "보증금", value: "없음", mValue: "없음" },
      {
        label: "관리비",
        value: "월 15만 원",
        note: "(1인실 기준)",
        mValue: "월 15만 원 (1인실)",
      },
    ],
    docs: [
      {
        name: "신분증 사본",
        note: "주민등록증 또는 운전면허증",
        mNote: "주민등록증 또는 운전면허증",
        ready: true,
      },
      {
        name: "사업계획서",
        note: "센터 양식 · 공고 원문에서 내려받기",
        mNote: "센터 양식 · 원문에서 내려받기",
        ready: true,
      },
      {
        name: "발표 자료",
        note: "발표 심사 대상자만 · 10분 분량",
        mNote: "발표 심사 대상자만",
        ready: false,
      },
      {
        name: "창업 교육 이수증",
        note: "있으면 가점이에요 · 선택",
        mNote: "있으면 가점 · 선택",
        ready: false,
      },
    ],
    currentStep: 1,
    schedule: [
      { step: 1, title: "접수", when: "11월 3일까지" },
      { step: 2, title: "서류 심사", when: "11월 둘째 주" },
      { step: 3, title: "발표 심사", when: "11월 넷째 주" },
      { step: 4, title: "입주", when: "12월 중" },
    ],
    rules: [
      {
        label: "창업 상태",
        rule: "예비 창업 또는 창업 3년 이내",
        mRule: "예비 또는 3년 이내",
        met: true,
      },
      { label: "업종", rule: "지식서비스 · 제조", mRule: "지식서비스 · 제조", met: true },
      { label: "대표자 나이", rule: "만 39세 이하", mRule: "만 39세 이하", met: true },
      { label: "사업장 소재지", rule: "서울 소재 또는 이전 예정", mRule: "", met: false },
    ],
    linkedSupport: {
      id: "f1",
      title: "예비창업 지원사업",
      desc: "최대 1억 원 · 선정되면 이 센터에 우선 입주",
      amount: "최대 1억 원",
    },
  },
];

/* ---------- 사업 정보 입력 ---------- */

export type BizOnboardingData = {
  /** 주거와 함께 쓰는 공통 정보 */
  common: { age: number; residence: string };
  industries: string[];
  provinces: string[];
  districts: string[];
  needs: string[];
  initialNeeds: string[];
  /** 창업 상태별 '지금 조건으로' 미리보기 */
  preview: Record<BizStage, { spaces: number; support: number; check: number }>;
};

export const bizOnboarding: BizOnboardingData = {
  common: { age: 29, residence: "서울 마포구" },
  industries: [
    "소프트웨어 개발 · IT 서비스",
    "음식점 · 카페",
    "소매 · 온라인 판매",
    "디자인 · 콘텐츠",
    "제조",
    "기타",
  ],
  provinces: ["서울특별시", "경기도", "인천광역시"],
  districts: ["마포구", "서대문구", "영등포구"],
  needs: ["사무실", "1인 오피스", "상가", "회의실"],
  initialNeeds: ["사무실"],
  preview: {
    pre: { spaces: 4, support: 3, check: 1 },
    run: { spaces: 3, support: 4, check: 2 },
  },
};
