// 공고 원문을 정리한 목차별 내용 (화면용 예시 데이터). 실제 값은 API에서 받아요.
// 추출 결과(extraction.completed)를 백엔드가 화면용으로 가공한 모양이에요.

/** 목차 섹션 */
export type NoticeSectionKey =
  | "eligibility"
  | "housing"
  | "schedule"
  | "apply"
  | "selection"
  | "cautions"
  | "living"
  | "contacts";

export type EligibilityCategory =
  | "AGE"
  | "HOME_OWNERSHIP"
  | "INCOME"
  | "ASSETS"
  | "CAR_ASSETS"
  | "RESIDENCE"
  | "HOUSEHOLD"
  | "NATIONALITY"
  | "OTHER";

export type NoticeHousingType = {
  /** 주택형 (예: 55, 26A) */
  code: string;
  /** 원문에 없으면 null (화면은 "원문 확인") */
  areaSqm: number | null;
  /** 이번에 모집하는 호수 */
  offered: number | null;
  depositWon: number | null;
  /** 호마다 다르면 가장 큰 값 (depositWon은 가장 작은 값) */
  depositMaxWon?: number;
  /** 보증금 중 계약할 때 내는 돈 */
  contractWon?: number;
  /** 보증금 중 입주 전에 내는 돈 */
  balanceWon?: number;
  monthlyRentWon: number | null;
  monthlyRentMaxWon?: number;
  /** 이 가격을 내는 대상 (예: 「수급자 등」). 대상마다 가격이 다를 때만 */
  target?: string;
  /** 내 조건으로 신청할 수 있는 주택형 */
  mine?: boolean;
};

export type NoticeScheduleItem = {
  id: string;
  label: string;
  /** YYYY-MM-DD. 원문에 없으면 null */
  start: string | null;
  end: string | null;
  /** 접수 시간 · 제외 요일 */
  time?: string;
  note?: string;
  /** 오늘 기준 진행 상태 (백엔드가 계산) */
  state: "done" | "now" | "todo";
};

export type NoticeDocumentGroup =
  "COMMON" | "CONDITIONAL" | "DIRECT" | "PROXY_SPOUSE" | "PROXY_OTHER";

export type NoticeDocumentItem = {
  id: string;
  name: string;
  /** 해당하는 경우 */
  when?: string;
  desc: string;
};

export type NoticeSelectionKind =
  "FIRST_COME" | "LOTTERY" | "PRIORITY" | "SCORE" | "TIE_BREAK" | "OTHER";

export type NoticeTextItem = { id: string; title: string; text: string };

export type NoticeDoc = {
  /** 오늘 기준 접수 상태 (백엔드가 계산) */
  status: "UPCOMING" | "OPEN" | "CLOSED";
  /** 신청 기간 */
  applyPeriod: { start: string; end: string; note?: string } | null;
  summary: string;
  source: {
    fileName: string;
    /** 우리 저장소에 옮겨 둔 PDF. 없으면 기관 사이트로 보내요 */
    pdfUrl: string | null;
    pageCount: number | null;
    /** 기관 공고 페이지 */
    detailUrl: string;
  };
  /** 섹션별 원문 쪽 번호 (1부터) */
  pages: Partial<Record<NoticeSectionKey, number>>;
  eligibility: { id: string; category: EligibilityCategory; text: string; detail?: string }[];
  housing: {
    id: string;
    complexName: string;
    address: string;
    /** 금액 기준 안내 */
    basis?: string;
    types: NoticeHousingType[];
  }[];
  schedule: NoticeScheduleItem[];
  apply: {
    method: string;
    /** 원문에 신청 방법이 없으면 null */
    channel: "ONLINE" | "ONSITE" | "EMAIL" | "MAIL" | "FAX" | null;
    /** 온라인 신청 주소 */
    url?: string;
    place?: { name: string; address: string };
    hours?: string;
    documents: { group: NoticeDocumentGroup; items: NoticeDocumentItem[] }[];
  };
  selection: { id: string; kind: NoticeSelectionKind; text: string }[];
  cautions: NoticeTextItem[];
  /** 입주 · 거주 안내 */
  living: NoticeTextItem[];
  contacts: { id: string; name: string; phone: string; desc: string }[];
};

/** 양산 삼성파크빌 국민임대 (추출 예시 데이터 그대로 가공) */
export const parkvilleDoc: NoticeDoc = {
  status: "OPEN",
  applyPeriod: { start: "2026-10-12", end: "2026-11-12", note: "현장 방문 · 10:00~16:00" },
  summary:
    "남은 세대를 방문 순서대로 동호를 고른 뒤 먼저 계약하고, 계약 후에 자격을 확인하는 국민임대 모집이에요.",
  source: {
    fileName: "양산삼성파크빌자격완화입주자모집(2026.09.30).pdf",
    pdfUrl: "/mock/notice-n7.pdf",
    pageCount: 8,
    detailUrl:
      "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=2015122300020825&ccrCnntSysDsCd=03&uppAisTpCd=06&aisTpCd=07&mi=1026",
  },
  pages: {
    eligibility: 3,
    housing: 2,
    schedule: 5,
    apply: 6,
    selection: 5,
    cautions: 1,
    living: 6,
    contacts: 2,
  },
  eligibility: [
    {
      id: "eligibility-homeless",
      category: "HOME_OWNERSHIP",
      text: "신청일 기준으로 세대구성원 모두 집이 없어야 해요. 공고일부터 계약이 끝날 때까지 유지해야 해요.",
      detail:
        "전용 60㎡ 이하, 공시가격 1억 원(수도권 1억 6천만 원) 이하 소형·저가주택은 집이 없는 것으로 봐요.",
    },
    {
      id: "eligibility-adult-age",
      category: "AGE",
      text: "만 19세 이상이어야 해요.",
      detail: "자녀가 있거나 형제자매를 부양하는 미성년 세대주 등은 신청할 수 있어요.",
    },
    {
      id: "eligibility-car-value",
      category: "CAR_ASSETS",
      text: "자동차가액이 4,542만 원 이하여야 해요.",
    },
    {
      id: "eligibility-income-waived",
      category: "INCOME",
      text: "이번 모집은 소득 기준이 없어요.",
    },
    {
      id: "eligibility-residence-unrestricted",
      category: "RESIDENCE",
      text: "사는 지역과 상관없이 신청할 수 있어요.",
    },
    {
      id: "eligibility-single-household",
      category: "HOUSEHOLD",
      text: "1인 가구도 신청할 수 있고, 단독세대주 면적 제한도 없어요.",
    },
    {
      id: "eligibility-foreign-applicant",
      category: "NATIONALITY",
      text: "외국인은 신청할 수 없어요.",
    },
    {
      id: "eligibility-illegal-transfer-bar",
      category: "OTHER",
      text: "세대구성원 중 공공임대 불법 양도·전대로 적발된 지 4년이 안 된 사람이 있으면 신청할 수 없어요.",
    },
  ],
  housing: [
    {
      id: "samsung-parkville",
      complexName: "삼성파크빌",
      address: "경상남도 양산시 두전길 42 (어곡동 8-1)",
      basis: "기본 임대조건 · 보증금과 월세를 바꾸는 전환 조건은 원문에서 확인해 주세요",
      types: [
        {
          code: "55",
          areaSqm: 55.68,
          offered: 32,
          depositWon: 18_551_000,
          contractWon: 500_000,
          balanceWon: 18_051_000,
          monthlyRentWon: 114_150,
          mine: true,
        },
      ],
    },
  ],
  schedule: [
    {
      id: "schedule-announcement",
      label: "공고",
      start: "2026-09-30",
      end: "2026-09-30",
      state: "done",
    },
    {
      id: "schedule-viewing",
      label: "세대 열람 · 샘플하우스",
      start: "2026-10-06",
      end: "2026-11-12",
      time: "10:00~16:00 (12~13시 제외) · 주말·공휴일 제외",
      note: "신분증을 들고 단지 관리사무소로 가요. 빈집이 다 나가면 일찍 끝나요",
      state: "now",
    },
    {
      id: "schedule-contract",
      label: "방문 신청 · 동호 지정 · 계약",
      start: "2026-10-12",
      end: "2026-11-12",
      time: "10:00~16:00 · 금요일·주말·공휴일 제외",
      note: "서류 제출과 계약금(50만 원) 입금도 같은 날 해요",
      state: "now",
    },
    {
      id: "schedule-eligibility-result-notice",
      label: "자격 확인 · 입주 안내",
      start: null,
      end: null,
      note: "계약 후 약 2개월 · 맞는 사람에게만 따로 알려줘요",
      state: "todo",
    },
    {
      id: "schedule-move-in-period",
      label: "입주 기간",
      start: "2026-12-14",
      end: "2027-01-14",
      note: "입주 전까지 잔금을 내요",
      state: "todo",
    },
  ],
  apply: {
    method:
      "인터넷 신청은 안 되고 현장 접수만 받아요. 신청 전에 관리사무소에 문의하고 세대를 꼭 열람해 주세요.",
    channel: "ONSITE",
    place: {
      name: "LH 경남양산권주거복지지사",
      address: "경남 양산시 물금읍 청운로 358, 국민연금공단 양산지사 2층",
    },
    hours: "10:00~16:00 · 금요일·주말·공휴일 제외",
    documents: [
      {
        group: "COMMON",
        items: [
          {
            id: "privacy-consent",
            name: "개인정보 수집·이용 및 제3자 제공 동의서 (LH 서식)",
            desc: "세대구성원 모두 서명해요. 만 14세 미만은 보호자가 서명해요.",
          },
          {
            id: "applicant-id",
            name: "신청자 신분증",
            desc: "주민등록증, 운전면허증, 여권만 인정해요.",
          },
          {
            id: "applicant-household-register",
            name: "주민등록표등본 (전부 표기)",
            desc: "세대구성 사유·일자, 세대주와의 관계, 주민등록번호, 전입일·변동일이 모두 나오게 떼요.",
          },
          {
            id: "applicant-stamp-direct",
            name: "본인 도장",
            when: "직접 신청할 때",
            desc: "서명으로 대신할 수 있어요.",
          },
        ],
      },
      {
        group: "CONDITIONAL",
        items: [
          {
            id: "spouse-household-register",
            name: "배우자 주민등록표등본",
            when: "배우자와 세대가 나뉘어 있을 때",
            desc: "1통 더 내요.",
          },
          {
            id: "prospective-spouse-household-register",
            name: "예비배우자 주민등록표등본",
            when: "예비신혼부부",
            desc: "1통 더 내요.",
          },
          {
            id: "notice-date-head-household-register",
            name: "공고일 당시 세대주의 주민등록표등본",
            when: "공고일 뒤에 세대주와 등본이 나뉘었을 때",
            desc: "1통 더 내요.",
          },
          {
            id: "applicant-resident-record-extract",
            name: "주민등록초본",
            when: "공고일 뒤에 주소나 세대구성원이 바뀌었을 때",
            desc: "1통 더 내요.",
          },
          {
            id: "family-relationship-certificate",
            name: "가족관계증명서 (상세)",
            when: "등본에서 배우자를 확인할 수 없거나 세대주가 아닐 때",
            desc: "예비신혼부부는 함께 살 세대원과의 관계를 확인할 수 있게 내요.",
          },
          {
            id: "foreign-spouse-registration-card-copy",
            name: "외국인등록증 사본",
            when: "배우자가 외국인일 때",
            desc: "배우자의 외국인등록증 사본을 내요.",
          },
        ],
      },
      {
        group: "PROXY_SPOUSE",
        items: [
          { id: "spouse-id", name: "신청자와 배우자 신분증", desc: "둘 다 가져가요." },
          {
            id: "applicant-stamp-spouse-proxy",
            name: "신청자 도장",
            desc: "신청자 본인 도장이에요.",
          },
          {
            id: "proxy-relationship-proof",
            name: "신청자와의 관계 증명서류",
            desc: "주민등록표등본 등으로 증명해요.",
          },
        ],
      },
      {
        group: "PROXY_OTHER",
        items: [
          {
            id: "proxy-seal-method",
            name: "인감증명서 + 위임장 + 인감도장",
            when: "인감증명 방식",
            desc: "위임장에는 인감증명서와 같은 도장을 찍어요.",
          },
          {
            id: "proxy-signature-method",
            name: "본인서명사실확인서 + 자필 서명 위임장",
            when: "본인서명 방식",
            desc: "수임인 서명란에 대리인 이름을 꼭 적어요.",
          },
          {
            id: "proxy-id",
            name: "신청자와 대리인 신분증",
            desc: "주민등록증, 운전면허증, 여권만 인정해요.",
          },
        ],
      },
    ],
  },
  selection: [
    {
      id: "selection-eligibility-check",
      kind: "FIRST_COME",
      text: "사는 곳·순위·배점과 상관없이 온 순서대로 동호를 골라 계약하고, 계약한 사람의 집·자동차 기준을 나중에 확인해요.",
    },
    {
      id: "selection-lottery-before-10",
      kind: "LOTTERY",
      text: "당일 오전 10시 전에 와서 명부에 서명한 사람이 2명 이상이면 추첨으로 순번을 정해요.",
    },
    {
      id: "selection-first-come-after-10",
      kind: "FIRST_COME",
      text: "오전 10시 뒤에 온 사람은 앞 순번이 끝난 뒤 남은 세대를 명부 순서대로 골라요.",
    },
    {
      id: "selection-tie-break-original-order",
      kind: "TIE_BREAK",
      text: "3번 불러도 대답이 없으면 다음 순번으로 넘어가요. 놓친 사람은 그날 마지막 순번 뒤에 고를 수 있어요.",
    },
    {
      id: "selection-unit-change-prohibited",
      kind: "OTHER",
      text: "순번이 되면 바로 동호를 골라야 하고, 고른 뒤에는 남은 세대가 있어도 바꿀 수 없어요.",
    },
  ],
  cautions: [
    {
      id: "caution-contract-deposit",
      title: "계약금은 당일 16시까지",
      text: "동호를 고른 날 16시까지 안내받은 계좌로 계약금 50만 원을 넣어야 해요. 현장 수납은 안 되고, 못 넣으면 고른 동호가 취소돼요.",
    },
    {
      id: "caution-documents-required",
      title: "서류는 계약 당일에 모두",
      text: "서류가 하나라도 빠지면 동호 지정과 계약을 할 수 없어요.",
    },
    {
      id: "caution-document-issue-date",
      title: "서류 발급일",
      text: "모든 서류는 공고일(9월 30일) 뒤에 뗀 것이어야 해요.",
    },
    {
      id: "caution-maintain-eligibility",
      title: "입주할 때까지 무주택 유지",
      text: "공고일부터 입주할 때까지 세대 모두 집이 없어야 해요. 못 지키면 당첨 취소나 계약 거절이 될 수 있어요.",
    },
    {
      id: "caution-duplicate-application",
      title: "한 세대에 한 집만",
      text: "중복 신청하면 모두 무효예요. 예비신혼부부는 둘 중 한 명만 대표로 신청해요.",
    },
    {
      id: "caution-contract-cancellation",
      title: "단순 변심 해지는 위약금",
      text: "자격이 맞다는 통보를 받은 뒤 단순 변심으로 해지하면 위약금을 빼고 돌려받아요.",
    },
    {
      id: "caution-existing-public-rental",
      title: "다른 공공임대에 살고 있다면",
      text: "입주 전에 살던 공공임대를 비워야 해요. 같은 세대 일부만 신청하면 입주 전에 세대를 나눠야 하고, 배우자는 나눠도 입주할 수 없어요.",
    },
  ],
  living: [
    {
      id: "move-in-key-and-charges",
      title: "입주와 열쇠",
      text: "잔금을 내고 이삿짐이 들어온 뒤 본인 확인을 하면 열쇠를 받아요. 입주 기간이 지나면 살지 않아도 다음 날부터 임대료와 관리비가 나와요.",
    },
    {
      id: "living-lease-term-and-renewal",
      title: "계약 기간과 갱신",
      text: "2년 계약이고, 입주 자격을 계속 갖추면 2년 단위로 갱신해요. 보증금과 월세는 법이 정한 범위에서 오를 수 있어요.",
    },
    {
      id: "living-management-fee",
      title: "관리비",
      text: "입주한 날부터 월세와 별도로 관리비가 나와요.",
    },
  ],
  contacts: [
    {
      id: "contact-parkville-management",
      name: "삼성파크빌 관리사무소",
      phone: "055-367-0335",
      desc: "세대 열람 전에 문의해요",
    },
    {
      id: "contact-lh-call-center",
      name: "LH 콜센터",
      phone: "1600-1004",
      desc: "신청 관련 문의",
    },
  ],
};

/** 행복주택 예시 */
export const happyHousingDoc: NoticeDoc = {
  status: "OPEN",
  applyPeriod: { start: "2026-10-14", end: "2026-10-31", note: "LH 청약플러스 온라인 신청" },
  summary: "청년·신혼부부에게 시세보다 싸게 빌려주는 행복주택 120호 입주자 모집이에요.",
  source: {
    fileName: "○○지구 행복주택 입주자모집공고.pdf",
    // 임시: 로컬 예시 PDF로 보여줘요 (쪽 번호는 실제와 달라요)
    pdfUrl: "/mock/notice-n7.pdf",
    pageCount: 8,
    detailUrl: "https://apply.lh.or.kr",
  },
  pages: {
    eligibility: 3,
    housing: 2,
    schedule: 5,
    apply: 6,
    selection: 5,
    cautions: 1,
    living: 7,
    contacts: 8,
  },
  eligibility: [
    {
      id: "age",
      category: "AGE",
      text: "청년은 만 19~39세 미혼, 신혼부부는 혼인 7년 이내예요.",
    },
    { id: "homeless", category: "HOME_OWNERSHIP", text: "세대구성원 모두 집이 없어야 해요." },
    {
      id: "income",
      category: "INCOME",
      text: "도시근로자 월평균소득 100% 이하예요. (1인 가구는 120%)",
    },
    {
      id: "assets",
      category: "ASSETS",
      text: "총자산 2억 5,100만 원 이하예요.",
    },
    { id: "car", category: "CAR_ASSETS", text: "자동차가액 4,542만 원 이하예요." },
  ],
  housing: [
    {
      id: "complex",
      complexName: "○○지구 행복주택",
      address: "서울 마포구 ○○동",
      basis: "청년 기준",
      types: [
        {
          code: "26A",
          areaSqm: 26.3,
          offered: 64,
          depositWon: 24_000_000,
          monthlyRentWon: 180_000,
          mine: true,
        },
        {
          code: "36B",
          areaSqm: 36.8,
          offered: 40,
          depositWon: 33_000_000,
          monthlyRentWon: 250_000,
        },
        {
          code: "44C",
          areaSqm: 44.1,
          offered: 16,
          depositWon: 40_000_000,
          monthlyRentWon: 300_000,
        },
      ],
    },
  ],
  schedule: [
    { id: "s1", label: "공고", start: "2026-10-07", end: "2026-10-07", state: "done" },
    { id: "s2", label: "접수", start: "2026-10-14", end: "2026-10-31", state: "now" },
    { id: "s3", label: "서류 제출", start: "2026-11-18", end: "2026-11-24", state: "todo" },
    { id: "s4", label: "당첨 발표", start: "2026-12-18", end: "2026-12-18", state: "todo" },
    { id: "s5", label: "계약", start: "2027-01-13", end: "2027-01-15", state: "todo" },
  ],
  apply: {
    method: "LH 청약플러스에서 온라인으로 신청해요. 모바일 앱으로도 할 수 있어요.",
    channel: "ONLINE",
    url: "https://apply.lh.or.kr",
    documents: [
      {
        group: "COMMON",
        items: [
          {
            id: "register",
            name: "주민등록표등본",
            desc: "서류 제출 대상자로 뽑히면 내요.",
          },
          {
            id: "consent",
            name: "금융정보 등 제공 동의서",
            desc: "세대구성원 모두 서명해요.",
          },
        ],
      },
    ],
  },
  selection: [
    { id: "p1", kind: "PRIORITY", text: "1순위: 해당 지역에 살거나 직장이 있어요." },
    { id: "p2", kind: "PRIORITY", text: "2순위: 서울에 살거나 직장이 있어요." },
    { id: "p3", kind: "LOTTERY", text: "같은 순위 안에서는 추첨으로 뽑아요." },
  ],
  cautions: [
    {
      id: "c1",
      title: "한 세대에 한 집만",
      text: "중복 신청하면 모두 무효예요.",
    },
  ],
  living: [
    {
      id: "l1",
      title: "거주 기간",
      text: "청년은 최대 6년, 자녀가 있으면 최대 10년까지 살 수 있어요.",
    },
  ],
  contacts: [{ id: "lh", name: "LH 콜센터", phone: "1600-1004", desc: "신청 관련 문의" }],
};

/** 청년 매입임대 예시 (주택은 주택목록에서 보여줘요) */
export const youthPurchaseDoc: NoticeDoc = {
  status: "OPEN",
  applyPeriod: { start: "2026-10-20", end: "2026-10-24", note: "LH 청약플러스 온라인 신청" },
  summary: "마포구 청년에게 빌라·원룸을 시세의 40~50%로 빌려주는 매입임대 8호 모집이에요.",
  source: {
    fileName: "2026년 2차 청년 매입임대주택 입주자모집공고.pdf",
    // 임시: 로컬 예시 PDF로 보여줘요 (쪽 번호는 실제와 달라요)
    pdfUrl: "/mock/notice-n7.pdf",
    pageCount: 8,
    detailUrl: "https://apply.lh.or.kr",
  },
  pages: { eligibility: 3, schedule: 5, apply: 6, selection: 5, living: 7, contacts: 8 },
  eligibility: [
    { id: "age", category: "AGE", text: "만 19~39세 미혼 청년이에요." },
    { id: "homeless", category: "HOME_OWNERSHIP", text: "본인이 집이 없어야 해요." },
    { id: "income", category: "INCOME", text: "1~3순위별 소득 기준이 달라요." },
  ],
  housing: [],
  schedule: [
    { id: "s1", label: "공고", start: "2026-10-10", end: "2026-10-10", state: "done" },
    { id: "s2", label: "접수", start: "2026-10-20", end: "2026-10-24", state: "now" },
    { id: "s3", label: "주택 공개", start: null, end: null, note: "11월 중", state: "todo" },
    { id: "s4", label: "당첨 발표", start: "2026-12-05", end: "2026-12-05", state: "todo" },
    { id: "s5", label: "계약", start: null, end: null, note: "12월 중", state: "todo" },
  ],
  apply: {
    method: "LH 청약플러스에서 온라인으로 신청해요.",
    channel: "ONLINE",
    url: "https://apply.lh.or.kr",
    documents: [],
  },
  selection: [
    { id: "p1", kind: "PRIORITY", text: "1순위: 수급자·차상위·한부모 가구" },
    { id: "p2", kind: "PRIORITY", text: "2순위: 본인과 부모 소득 합이 월평균소득 100% 이하" },
    { id: "p3", kind: "PRIORITY", text: "3순위: 본인 소득이 월평균소득 100% 이하" },
    { id: "p4", kind: "SCORE", text: "같은 순위 안에서는 배점이 높은 순서로 뽑아요." },
  ],
  cautions: [],
  living: [{ id: "l1", title: "거주 기간", text: "2년 계약, 최대 6년까지 살 수 있어요." }],
  contacts: [{ id: "lh", name: "LH 콜센터", phone: "1600-1004", desc: "신청 관련 문의" }],
};
