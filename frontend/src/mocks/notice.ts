// 화면용 예시 데이터 (디자인 WebDetail · WebDetailUnits · MDetail · MDetailUnits). 실제 값은 API에서 받아요.
import type { Verdict } from "@/components/ui/Badge";
import { happyHousingDoc, parkvilleDoc, youthPurchaseDoc, type NoticeDoc } from "./notice-doc";

export type NoticeFact = { label: string; value: string };

export type NoticeEligibility = {
  /** PC 문구 */
  label: string;
  /** 모바일 문구(짧은 버전) */
  shortLabel: string;
  /** met: 충족 · input: 정보를 넣어야 확인돼요 */
  status: "met" | "input";
};

export type NoticeRankTier = {
  rank: number;
  desc: string;
  /** mine: 내 순위 · no: 해당 안 됨 · check: 확인 필요 · none: 표시 없음 */
  state: "mine" | "no" | "check" | "none";
};

export type NoticeRanking = {
  myRank: number;
  reason: string;
  tiers: NoticeRankTier[];
  /** 같은 순위 안에서 뽑는 방법 */
  tieBreak: "추첨" | "배점";
  sourcePage: number;
};

/** 지도 위 위치(%) */
export type MapPoint = { x: number; y: number };

export type NoticeUnit = MapPoint & {
  id: string;
  name: string;
  /** 호 표기 (예: A동 214호). 단지별로 묶어 보여줄 때 */
  label?: string;
  siteName?: string;
  /** 가격 대상이 여럿이면 대상별 보증금·월세 */
  prices?: { target: string; deposit: string; rent: string }[];
  /** 모바일 지도 말풍선용 짧은 이름 */
  short?: string;
  addr?: string;
  type: string;
  area: string;
  floor: string;
  elevator?: string;
  deposit: string;
  rent: string;
  station: string;
  /** 모바일 목록용 짧은 표기 */
  stationShort?: string;
  /** 모바일 지도에서 위치가 다르면 */
  mobilePos?: MapPoint;
  /** true: 내 조건으로 신청 가능 · false: 다른 대상 */
  ok: boolean;
  /** 단지·건물 (sites[].id). 실제 API에서만 */
  siteId?: string;
  /** 단지 생활권 총점. 실제 API에서만 */
  lifeScore?: number;
  otherTarget: string;
  prep: string;
};

type NoticeBase = {
  id: string;
  /** 목업 판정 (실제 판정은 POST /eligibility/notices/{id}/evaluate) */
  verdict: Verdict;
  dday: number;
  /** 마감 표시를 바꿀 때 (상시 · 접수 예정 · 마감). 없으면 "마감 D-n" */
  dueLabel?: string;
  tags: string[];
  title: string;
  meta: string;
  /** 공고 원문을 낸 기관(버튼 문구에 써요) */
  agency: string;
  facts: NoticeFact[];
  /** 목업 판정 */
  eligibility: NoticeEligibility[];
  /** 순위로 뽑는 공고만 (선착순 · 추첨만 하는 공고는 없어요) */
  ranking?: NoticeRanking;
  /** 공고 원문을 목차별로 정리한 내용 */
  doc: NoticeDoc;
};

/** 단지 하나의 생활권 총점. 항목 점수·가까운 시설은 areaId로 따로 불러와요 (GET /areas/sites/{areaId}) */
export type NoticeLifeSite = {
  /** sites[].id */
  id: string;
  /** area 위치 ID. 아직 위치를 못 찾았으면 null */
  areaId: string | null;
  name: string;
  score: number;
  /** 세권 태그 이름 (역세권 · 숲세권 …) */
  tags: string[];
};

export type NoticeBenefit = {
  id: string;
  title: string;
  desc: string;
  verdict: Verdict;
};

export type NoticeMoney = {
  type: string;
  deposit: string;
  /** 받을 수 있는 대출이 없으면 대출 줄을 숨겨요 */
  loanName?: string;
  loanShortName?: string;
  loan?: string;
  prep: string;
  note: string;
};

/** 일반 공고: 주택형별 임대 조건(doc.housing) + (있으면) 블록별 공급 주택 */
export type StandardNotice = NoticeBase & {
  kind: "standard";
  /** 단지 안 블록별 공급 주택. 없으면 목록·지도 칸을 숨겨요 */
  units?: NoticeUnit[];
  /** 목업 준비할 돈 (실제는 판정 응답의 주택형별 준비할 돈) */
  money?: NoticeMoney;
  /** 생활권 점수가 아직 없으면 칸을 숨겨요. 단지가 여럿이면 score는 가장 높은 단지, min은 가장 낮은 단지 (높은 순 sites) */
  life?: { score: number; min: number; sites: NoticeLifeSite[] };
  benefitArea?: string;
  /** 혜택 판정이 아직 없으면 칸을 숨겨요 */
  benefits?: NoticeBenefit[];
  /** 단지·건물 위치 (실제 API). 좌표를 모르면 lat·lng가 null */
  sites?: NoticeSite[];
  /** 호별 주택목록이 있는지 (실제 API: GET /notices/{id}/units로 받아요) */
  hasUnits?: boolean;
};

export type NoticeSite = {
  id: string;
  name: string;
  lat: number | null;
  lng: number | null;
  /** 생활권 총점 (아직 없으면 없음) */
  lifeScore?: number;
};

/** 주택목록(엑셀)이 붙은 공고 */
export type UnitListNotice = NoticeBase & {
  kind: "units";
  units: NoticeUnit[];
};

export type Notice = StandardNotice | UnitListNotice;

const happyHousing: Omit<StandardNotice, "id"> = {
  kind: "standard",
  verdict: "ok",
  dday: 12,
  tags: ["역세권", "편세권"],
  title: "○○지구 행복주택",
  meta: "LH · 공공임대 월세형 · 서울 마포구 · 직장까지 32분",
  agency: "LH",
  doc: happyHousingDoc,
  facts: [
    { label: "모집 대상", value: "청년 · 신혼부부" },
    { label: "공급 호수", value: "120호" },
    { label: "전용면적", value: "26 ~ 44㎡" },
    { label: "거주 기간", value: "최대 6년" },
  ],
  eligibility: [
    { label: "나이 · 청년 유형", shortLabel: "나이 · 청년 유형", status: "met" },
    { label: "소득 · 중위소득 100% 이하", shortLabel: "소득 · 중위 100% 이하", status: "met" },
    { label: "무주택", shortLabel: "무주택", status: "met" },
    { label: "자산 · 자동차 가액 포함", shortLabel: "자산 · 자동차 포함", status: "input" },
  ],
  ranking: {
    myRank: 1,
    reason: "마포구에 살고 있어서 가장 높은 순위예요",
    tiers: [
      { rank: 1, desc: "마포구에 살거나 직장이 있어요", state: "mine" },
      { rank: 2, desc: "서울에 살거나 직장이 있어요", state: "none" },
      { rank: 3, desc: "그 밖의 지역", state: "none" },
    ],
    tieBreak: "추첨",
    sourcePage: 7,
  },
  money: {
    type: "26A",
    deposit: "2,400만 원",
    loanName: "버팀목 전세자금 대출 예상",
    loanShortName: "버팀목 대출 예상",
    loan: "1,440만 원",
    prep: "960만 원",
    note: "월 임대료 18만 원 · 주변 시세의 72% 수준",
  },
  life: {
    score: 82,
    min: 82,
    sites: [
      {
        id: "main",
        areaId: "mock-area-1",
        name: "마포 행복주택",
        score: 82,
        tags: ["역세권", "숲세권"],
      },
    ],
  },
  benefitArea: "서울 마포구",
  benefits: [
    { id: "b1", title: "청년 월세 지원", desc: "월 최대 20만 원 · 전입 후 신청", verdict: "ok" },
    { id: "b3", title: "이사비 · 중개보수 지원", desc: "최대 40만 원 · 1회", verdict: "ok" },
    { id: "b4", title: "청년 정착 지원금", desc: "전입 후 6개월부터", verdict: "check" },
  ],
};

const blockUnit = (
  id: string,
  name: string,
  type: string,
  floor: string,
  station: string,
  ok: boolean,
  x: number,
  y: number,
): NoticeUnit => {
  const row: Record<string, { area: string; deposit: string; rent: string; prep: string }> = {
    "26A": { area: "26.3㎡", deposit: "2,400만 원", rent: "18만 원", prep: "960만 원" },
    "36B": { area: "36.8㎡", deposit: "3,300만 원", rent: "25만 원", prep: "1,320만 원" },
    "44C": { area: "44.1㎡", deposit: "4,000만 원", rent: "30만 원", prep: "1,600만 원" },
  };
  return {
    id,
    name,
    type,
    area: row[type].area,
    floor,
    deposit: row[type].deposit,
    rent: `월 ${row[type].rent}`,
    station,
    ok,
    otherTarget: "신혼부부 대상",
    x,
    y,
    prep: row[type].prep,
  };
};

const blockUnits: NoticeUnit[] = [
  blockUnit("u1", "A-1블록 101동 302호", "26A", "3층", "○○역 도보 6분", true, 22, 30),
  blockUnit("u2", "A-1블록 103동 1104호", "26A", "11층", "○○역 도보 8분", true, 36, 22),
  blockUnit("u3", "A-2블록 201동 705호", "36B", "7층", "○○역 도보 5분", false, 66, 28),
  blockUnit("u4", "A-2블록 203동 402호", "26A", "4층", "○○역 도보 4분", true, 78, 38),
  blockUnit("u5", "B-1블록 301동 908호", "44C", "9층", "○○역 도보 9분", false, 34, 72),
  blockUnit("u6", "B-1블록 302동 210호", "26A", "2층", "○○역 도보 7분", true, 54, 78),
];

const youthPurchase: Omit<UnitListNotice, "id"> = {
  kind: "units",
  verdict: "ok",
  dday: 5,
  tags: ["주택목록 있음"],
  title: "2026년 2차 청년 매입임대주택",
  meta: "LH 서울지역본부 · 서울 마포구 · 접수 10월 20일 ~ 24일",
  agency: "LH",
  doc: youthPurchaseDoc,
  facts: [
    { label: "모집 대상", value: "청년 · 신혼부부" },
    { label: "공급 주택", value: "8호" },
    { label: "거주 기간", value: "최대 6년" },
  ],
  eligibility: [
    { label: "청년 (만 19~39세, 미혼)", shortLabel: "청년 (만 19~39세, 미혼)", status: "met" },
    { label: "소득 · 중위소득 100% 이하", shortLabel: "소득 · 중위 100% 이하", status: "met" },
    { label: "무주택", shortLabel: "무주택", status: "met" },
  ],
  ranking: {
    myRank: 3,
    reason: "부모님 소득을 넣으면 2순위가 될 수 있어요",
    tiers: [
      { rank: 1, desc: "수급자 · 차상위 · 한부모 가구", state: "no" },
      { rank: 2, desc: "본인 + 부모 소득 합 중위 100% 이하", state: "check" },
      { rank: 3, desc: "본인 소득 중위 100% 이하", state: "mine" },
    ],
    tieBreak: "배점",
    sourcePage: 5,
  },
  units: [
    {
      id: "u1",
      name: "성산동 ○○빌라 302호",
      short: "성산동 302호",
      addr: "서울 마포구 성산동",
      type: "원룸",
      area: "29.8㎡",
      floor: "3층",
      elevator: "승강기 있음",
      deposit: "100만 원",
      rent: "월 12만 원",
      station: "망원역 도보 7분",
      stationShort: "망원역 7분",
      ok: true,
      otherTarget: "신혼부부 대상",
      x: 30,
      y: 46,
      prep: "100만 원",
    },
    {
      id: "u2",
      name: "망원동 ○○하우스 201호",
      short: "망원동 201호",
      addr: "서울 마포구 망원동",
      type: "원룸",
      area: "27.5㎡",
      floor: "2층",
      elevator: "승강기 없음",
      deposit: "100만 원",
      rent: "월 11만 원",
      station: "망원역 도보 4분",
      stationShort: "망원역 4분",
      ok: true,
      otherTarget: "신혼부부 대상",
      x: 20,
      y: 56,
      prep: "100만 원",
      mobilePos: { x: 20, y: 60 },
    },
    {
      id: "u3",
      name: "서교동 ○○빌 401호",
      short: "서교동 401호",
      addr: "서울 마포구 서교동",
      type: "원룸",
      area: "31.0㎡",
      floor: "4층",
      elevator: "승강기 있음",
      deposit: "100만 원",
      rent: "월 14만 원",
      station: "홍대입구역 도보 9분",
      stationShort: "홍대입구역 9분",
      ok: true,
      otherTarget: "신혼부부 대상",
      x: 55,
      y: 48,
      prep: "100만 원",
      mobilePos: { x: 58, y: 50 },
    },
    {
      id: "u4",
      name: "연남동 ○○맨션 102호",
      short: "연남동 102호",
      addr: "서울 마포구 연남동",
      type: "투룸",
      area: "44.6㎡",
      floor: "1층",
      elevator: "승강기 없음",
      deposit: "250만 원",
      rent: "월 21만 원",
      station: "홍대입구역 도보 6분",
      stationShort: "홍대입구역 6분",
      ok: false,
      otherTarget: "신혼부부 대상",
      x: 62,
      y: 22,
      prep: "250만 원",
      mobilePos: { x: 66, y: 24 },
    },
    {
      id: "u5",
      name: "합정동 ○○빌라 303호",
      short: "합정동 303호",
      addr: "서울 마포구 합정동",
      type: "원룸",
      area: "28.2㎡",
      floor: "3층",
      elevator: "승강기 있음",
      deposit: "100만 원",
      rent: "월 13만 원",
      station: "합정역 도보 5분",
      stationShort: "합정역 5분",
      ok: true,
      otherTarget: "신혼부부 대상",
      x: 40,
      y: 70,
      prep: "100만 원",
      mobilePos: { x: 42, y: 74 },
    },
    {
      id: "u6",
      name: "상수동 ○○하임 205호",
      short: "상수동 205호",
      addr: "서울 마포구 상수동",
      type: "원룸",
      area: "26.4㎡",
      floor: "2층",
      elevator: "승강기 없음",
      deposit: "100만 원",
      rent: "월 12만 원",
      station: "상수역 도보 3분",
      stationShort: "상수역 3분",
      ok: true,
      otherTarget: "신혼부부 대상",
      x: 56,
      y: 80,
      prep: "100만 원",
      mobilePos: { x: 60, y: 84 },
    },
    {
      id: "u7",
      name: "중동 ○○빌 501호",
      short: "중동 501호",
      addr: "서울 마포구 중동",
      type: "투룸",
      area: "46.1㎡",
      floor: "5층",
      elevator: "승강기 있음",
      deposit: "300만 원",
      rent: "월 23만 원",
      station: "디지털미디어시티역 도보 11분",
      stationShort: "디지털미디어시티역 11분",
      ok: false,
      otherTarget: "신혼부부 대상",
      x: 16,
      y: 18,
      prep: "300만 원",
    },
    {
      id: "u8",
      name: "성산동 ○○파크 104호",
      short: "성산동 104호",
      addr: "서울 마포구 성산동",
      type: "원룸",
      area: "28.9㎡",
      floor: "1층",
      elevator: "승강기 없음",
      deposit: "100만 원",
      rent: "월 11만 원",
      station: "마포구청역 도보 8분",
      stationShort: "마포구청역 8분",
      ok: true,
      otherTarget: "신혼부부 대상",
      x: 36,
      y: 25,
      prep: "100만 원",
    },
  ],
};

/** 실제 추출 데이터로 만든 예시: 선착순 · 순위 없음 · 원문 PDF 있음 */
const parkville: Omit<StandardNotice, "id"> = {
  kind: "standard",
  verdict: "ok",
  dday: 20,
  tags: ["선착순", "소득·자산 기준 없음"],
  title: "양산 삼성파크빌 국민임대 선착순 모집",
  meta: "LH 경남지역본부 · 국민임대 · 경남 양산시",
  agency: "LH",
  doc: parkvilleDoc,
  facts: [
    { label: "보증금", value: "1,855만 원" },
    { label: "월 임대료", value: "11만 4,150원" },
    { label: "모집 호수", value: "32호" },
    { label: "전용면적", value: "55.68㎡" },
  ],
  eligibility: [
    { label: "무주택", shortLabel: "무주택", status: "met" },
    { label: "나이 · 만 19세 이상", shortLabel: "만 19세 이상", status: "met" },
    { label: "자동차가액 4,542만 원 이하", shortLabel: "자동차 4,542만 원 이하", status: "input" },
  ],
  money: {
    type: "55형",
    deposit: "1,855만 원",
    loanName: "버팀목 전세자금 대출 예상",
    loanShortName: "버팀목 대출 예상",
    loan: "1,100만 원",
    prep: "755만 원",
    note: "계약금 50만 원은 계약 당일에 넣어요 · 월 임대료 11만 4,150원",
  },
  life: {
    score: 64,
    min: 52,
    sites: [
      { id: "a", areaId: "mock-area-2", name: "사송 A-2블록", score: 64, tags: ["숲세권"] },
      { id: "b", areaId: "mock-area-3", name: "사송 B-1블록", score: 52, tags: [] },
    ],
  },
  benefitArea: "경남 양산시",
  benefits: [
    { id: "b1", title: "청년 월세 지원", desc: "월 최대 20만 원 · 전입 후 신청", verdict: "check" },
    { id: "b3", title: "이사비 · 중개보수 지원", desc: "최대 40만 원 · 1회", verdict: "ok" },
  ],
};

export const notices: Notice[] = [
  // 블록별 공급 주택이 있는 일반 공고
  { ...happyHousing, id: "n1", units: blockUnits },
  // 원문 PDF · 목차가 모두 있는 공고 (실제 추출 데이터)
  { ...parkville, id: "n7" },
  // 공급 주택 목록이 없는 일반 공고
  {
    ...happyHousing,
    id: "n2",
    dday: 20,
    tags: ["역세권"],
    title: "○○ 국민임대 예비입주자 모집",
    meta: "SH · 국민임대 · 서울 마포구 · 직장까지 32분",
    agency: "SH",
  },
  {
    ...happyHousing,
    id: "n3",
    dday: 9,
    tags: ["역세권", "편세권"],
    title: "○○ 장기전세",
    meta: "GH · 장기전세 · 서울 마포구 · 직장까지 32분",
    agency: "GH",
  },
  // 주택목록(엑셀)이 붙은 공고 → 주택목록 화면
  { ...youthPurchase, id: "n4" },
  {
    ...happyHousing,
    id: "n5",
    dday: 15,
    tags: ["역세권"],
    title: "○○ 청년 전세임대",
    meta: "LH · 청년 전세임대 · 서울 마포구 · 직장까지 32분",
    agency: "LH",
  },
  {
    ...happyHousing,
    id: "n6",
    dday: 25,
    tags: ["편세권"],
    title: "○○지구 공공분양",
    meta: "LH · 공공분양 · 서울 마포구 · 직장까지 32분",
    agency: "LH",
  },
];
