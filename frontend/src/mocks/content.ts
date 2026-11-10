// 화면용 예시 데이터 (디자인 WebNotices · MNotices · WebFaq · MFaq · WebStates · MStates). 실제 값은 API에서 받아요.
import type { NearMiss } from "@/components/states/NoMatchState";
import { routes } from "@/lib/routes";

/* 공지사항 */

export type AnnouncementCategory = "업데이트" | "점검" | "안내";

export type Announcement = {
  id: string;
  category: AnnouncementCategory;
  pinned: boolean;
  date: string;
  title: string;
  /** PC 본문 문단 */
  body: string[];
  /** PC 본문 아래 요점 목록 */
  points: string[];
  /** 모바일 본문 문단(짧게 줄인 글) */
  mobileBody: string[];
  cta?: { label: string; href: string };
};

export const announcementCategories = ["전체", "업데이트", "점검", "안내"] as const;
export type AnnouncementFilter = (typeof announcementCategories)[number];

export const announcements: Announcement[] = [
  {
    id: "n1",
    category: "점검",
    pinned: true,
    date: "2026.10.18",
    title: "10월 26일(일) 새벽 2시~5시 서비스 점검",
    body: [
      "더 안정적인 서비스를 위해 서버 점검을 해요. 점검 시간에는 무주택자들에 접속할 수 없어요.",
      "점검 중 마감되는 공고는 없지만, 그 시간에 나온 새 공고 알림은 점검이 끝난 뒤 한꺼번에 보내드려요.",
    ],
    points: [
      "점검 시간 · 10월 26일(일) 02:00 ~ 05:00",
      "영향 · 웹과 앱 접속, 알림 발송",
      "점검이 일찍 끝나면 바로 다시 열어요",
    ],
    mobileBody: [
      "점검 시간에는 무주택자들에 접속할 수 없어요.",
      "그 시간에 나온 새 공고 알림은 점검이 끝난 뒤 한꺼번에 보내드려요.",
    ],
  },
  {
    id: "n2",
    category: "업데이트",
    pinned: false,
    date: "2026.10.20",
    title: "사업공간 메뉴가 생겼어요",
    body: [
      "창업 공간, 공공 상가, 회의실과 사업 지원도 내 조건으로 찾을 수 있어요.",
      "위쪽의 ‘주거 · 사업공간’ 버튼으로 바꿔서 볼 수 있어요. 사업 정보는 따로 입력하고, 나이와 사는 곳은 주거와 함께 써요.",
    ],
    points: [
      "창업보육센터 · 청년창업센터 입주 모집",
      "LH · SH 단지 내 상가 입찰",
      "창업 지원금 · 정책자금 · 세금 감면",
    ],
    mobileBody: [
      "창업 공간, 공공 상가, 회의실과 사업 지원도 내 조건으로 찾을 수 있어요.",
      "위쪽의 주거 · 사업공간 버튼으로 바꿔서 볼 수 있어요.",
    ],
    cta: { label: "사업공간 둘러보기", href: routes.business },
  },
  {
    id: "n3",
    category: "업데이트",
    pinned: false,
    date: "2026.10.15",
    title: "경북·경남 지방 공사 공고도 이제 모아요",
    body: [
      "경상북도개발공사와 경남개발공사의 임대·분양 공고를 새로 모아요.",
      "이 지역에 사는 분은 조건에 맞는 공고가 나오면 알림으로 받아볼 수 있어요.",
    ],
    points: [],
    mobileBody: ["경상북도개발공사와 경남개발공사의 임대·분양 공고를 새로 모아요."],
    cta: { label: "내 집 보기", href: routes.homes },
  },
  {
    id: "n4",
    category: "안내",
    pinned: false,
    date: "2026.10.10",
    title: "개인정보처리방침이 11월 1일부터 바뀌어요",
    body: [
      "사업공간 기능이 생기면서 사업 정보(창업 상태, 업종, 희망 지역)를 새로 받게 되어 처리방침을 고쳐요.",
      "바뀐 내용은 11월 1일부터 적용돼요. 동의하지 않으면 그 전에 회원 탈퇴를 할 수 있어요.",
    ],
    points: [
      "처리 항목에 사업 정보 추가 (선택)",
      "사업 정보 보유 기간 · 회원 탈퇴 시까지",
      "그 밖의 내용은 그대로예요",
    ],
    mobileBody: [
      "사업 정보(창업 상태, 업종, 희망 지역)를 선택 항목으로 새로 받게 되어 처리방침을 고쳐요.",
    ],
    cta: { label: "개인정보처리방침 보기", href: routes.privacy },
  },
  {
    id: "n5",
    category: "안내",
    pinned: false,
    date: "2026.10.01",
    title: "하반기 청년 월세 지원 신청이 시작됐어요",
    body: [
      "국토교통부 청년 월세 지원 하반기 신청을 받아요. 내 혜택에서 받을 수 있는지 바로 확인해 보세요.",
      "지자체 청년 월세 지원과는 함께 받을 수 없으니, 금액과 기간을 비교해서 하나를 골라주세요.",
    ],
    points: [],
    mobileBody: ["내 혜택에서 받을 수 있는지 바로 확인해 보세요."],
    cta: { label: "내 혜택 보기", href: routes.benefits },
  },
  {
    id: "n6",
    category: "업데이트",
    pinned: false,
    date: "2026.09.22",
    title: "청약 가점 계산기를 새로 만들었어요",
    body: [
      "무주택 기간, 부양가족 수, 청약통장 가입 기간을 넣으면 내 가점을 계산해요.",
      "조건 입력에 넣은 정보가 있으면 자동으로 채워져요.",
    ],
    points: [],
    mobileBody: ["조건 입력에 넣은 정보가 있으면 자동으로 채워져요."],
    cta: { label: "가점 계산하기", href: routes.score },
  },
];

/* 자주 묻는 질문 */

export const faqCategories = [
  "전체",
  "판정·자격",
  "공고·혜택",
  "계정·개인정보",
  "알림",
  "사업공간",
] as const;
export type FaqFilter = (typeof faqCategories)[number];
export type FaqCategory = Exclude<FaqFilter, "전체">;

export type FaqItem = {
  id: string;
  category: FaqCategory;
  question: string;
  answer: string;
  link?: { label: string; href: string };
};

export type FaqData = {
  /** PC: 자세한 답 */
  web: FaqItem[];
  /** 모바일: 짧게 줄인 질문과 답 */
  mobile: FaqItem[];
  /** 처음 펼쳐 둘 질문 */
  initiallyOpen: string[];
  contact: { email: string; hours: string };
};

export const faq: FaqData = {
  initiallyOpen: ["f1"],
  contact: { email: "help@example.com", hours: "평일 10시~18시" },
  web: [
    {
      id: "f1",
      category: "판정·자격",
      question: "판정 결과는 믿어도 되나요?",
      answer:
        "공고와 정책 원문을 바탕으로 판정하고, 판정마다 근거 문장을 함께 보여드려요. 다만 최종 자격은 기관 심사로 정해져요. 신청 전에 원문을 꼭 확인해 주세요.",
    },
    {
      id: "f2",
      category: "판정·자격",
      question: "‘확인 필요’는 무슨 뜻인가요?",
      answer:
        "입력하지 않은 정보가 있거나, 원문만으로는 판단하기 어려운 조건이 있다는 뜻이에요. 어떤 조건 때문인지 상세 화면에 적어두었어요. 정보를 더 넣으면 판정이 바뀔 수 있어요.",
      link: { label: "조건 더 입력하기", href: routes.profile },
    },
    {
      id: "f3",
      category: "판정·자격",
      question: "소득은 세전인가요, 세후인가요?",
      answer:
        "세전 연소득이에요. 작년 원천징수영수증의 총급여를 넣으면 가장 정확해요. 정책마다 소득 기준(본인·가구·원가구)이 달라서 필요한 경우 따로 물어봐요.",
    },
    {
      id: "f4",
      category: "공고·혜택",
      question: "어느 지역 공고까지 나오나요?",
      answer:
        "LH와 청약홈은 전국 공고를, 지방 공사는 서울·경기·인천·부산·대구·대전·울산·경북·경남 공고를 모아요. 지역은 계속 늘려갈게요.",
    },
    {
      id: "f5",
      category: "공고·혜택",
      question: "새 공고는 얼마나 빨리 올라오나요?",
      answer:
        "평일 근무 시간에는 기관 게시판을 매시간 확인해요. 새 공고는 내용을 검수한 뒤 올라와서, 기관 게시보다 조금 늦을 수 있어요.",
    },
    {
      id: "f6",
      category: "공고·혜택",
      question: "여기서 바로 신청할 수 있나요?",
      answer:
        "아니요. 무주택자들은 찾고 판정하는 서비스예요. 신청은 각 기관 사이트에서 해요. 공고 상세의 ‘신청하러 가기’를 누르면 해당 페이지로 이동해요.",
    },
    {
      id: "f7",
      category: "계정·개인정보",
      question: "회원가입을 해야 하나요?",
      answer:
        "아니요. 로그인 없이 조건을 입력하면 바로 결과를 볼 수 있어요. 입력한 조건은 이 기기에 30일 동안 저장돼요. 관심 공고와 알림을 저장하고 싶을 때만 카카오·네이버·Google로 로그인하면 돼요. 비밀번호는 만들지 않아요.",
      link: { label: "로그인 없이 시작하기", href: routes.profile },
    },
    {
      id: "f8",
      category: "계정·개인정보",
      question: "소득·자산 정보는 저장되나요?",
      answer:
        "아니요. 소득·자산은 판정할 때만 쓰고 어디에도 저장하지 않아요. 탭을 닫으면 지워져요. 나이·지역 같은 나머지 조건은 이 기기에만 30일 동안 저장하고, 내 정보에서 언제든 지울 수 있어요.",
      link: { label: "개인정보처리방침 보기", href: routes.privacy },
    },
    {
      id: "f9",
      category: "계정·개인정보",
      question: "회원 탈퇴는 어떻게 하나요?",
      answer:
        "내 정보 › 개인정보에서 탈퇴할 수 있어요. 탈퇴하면 계정·관심 공고·알림 설정이 바로 지워지고, 이 기기에 저장한 조건도 함께 지워져요.",
      link: { label: "내 정보로 가기", href: `${routes.me}?tab=privacy` },
    },
    {
      id: "f10",
      category: "알림",
      question: "알림이 너무 많아요",
      answer:
        "내 정보 › 알림 설정에서 받을 알림 종류를 고르고, 밤 시간에는 방해 금지를 켤 수 있어요.",
      link: { label: "알림 설정", href: `${routes.me}?tab=notifications` },
    },
    {
      id: "f11",
      category: "알림",
      question: "마감 알림은 언제 오나요?",
      answer: "관심 등록한 공고와 혜택은 마감 7일 전, 1일 전에 알려드려요.",
    },
    {
      id: "f12",
      category: "사업공간",
      question: "아직 사업자등록 전인데 쓸 수 있나요?",
      answer: "네. 예비 창업으로 고르면 예비 창업자가 지원할 수 있는 공간과 지원사업을 보여드려요.",
      link: { label: "사업 정보 입력", href: routes.bizOnboarding },
    },
  ],
  mobile: [
    {
      id: "f1",
      category: "판정·자격",
      question: "판정 결과는 믿어도 되나요?",
      answer:
        "원문을 바탕으로 판정하고 근거 문장을 함께 보여드려요. 최종 자격은 기관 심사로 정해지니 신청 전에 원문을 꼭 확인해 주세요.",
    },
    {
      id: "f2",
      category: "판정·자격",
      question: "‘확인 필요’는 무슨 뜻인가요?",
      answer:
        "입력하지 않은 정보가 있거나 원문만으로 판단하기 어려운 조건이 있다는 뜻이에요. 정보를 더 넣으면 판정이 바뀔 수 있어요.",
      link: { label: "조건 더 입력하기", href: routes.profile },
    },
    {
      id: "f3",
      category: "판정·자격",
      question: "소득은 세전인가요?",
      answer: "세전 연소득이에요. 작년 원천징수영수증의 총급여를 넣으면 가장 정확해요.",
    },
    {
      id: "f4",
      category: "공고·혜택",
      question: "어느 지역 공고까지 나오나요?",
      answer:
        "LH와 청약홈은 전국, 지방 공사는 서울·경기·인천·부산·대구·대전·울산·경북·경남 공고를 모아요.",
    },
    {
      id: "f5",
      category: "공고·혜택",
      question: "여기서 바로 신청할 수 있나요?",
      answer:
        "아니요. 신청은 각 기관 사이트에서 해요. 공고 상세에서 원문으로 바로 이동할 수 있어요.",
    },
    {
      id: "f6",
      category: "계정·개인정보",
      question: "회원가입을 해야 하나요?",
      answer:
        "아니요. 로그인 없이 바로 결과를 볼 수 있어요. 조건은 이 기기에 저장돼요. 관심 공고와 알림을 저장할 때만 간편 로그인하면 돼요(비밀번호 없음).",
    },
    {
      id: "f7",
      category: "계정·개인정보",
      question: "소득·자산 정보는 저장되나요?",
      answer: "아니요. 판정할 때만 쓰고 저장하지 않아요. 탭을 닫으면 지워져요.",
      link: { label: "개인정보처리방침", href: routes.privacy },
    },
    {
      id: "f8",
      category: "알림",
      question: "마감 알림은 언제 오나요?",
      answer: "관심 등록한 공고와 혜택은 마감 7일 전, 1일 전에 알려드려요.",
    },
    {
      id: "f9",
      category: "사업공간",
      question: "사업자등록 전인데 쓸 수 있나요?",
      answer: "네. 예비 창업으로 고르면 지원할 수 있는 공간과 지원사업을 보여드려요.",
      link: { label: "사업 정보 입력", href: routes.bizOnboarding },
    },
  ],
};

/* 빈 상태 · 오류 미리보기 (WebStates · MStates) */

export type StatesPreview = {
  missingCount: number;
  nearMisses: NearMiss[];
  error: { code: string; at: string };
};

export const statesPreview: StatesPreview = {
  missingCount: 2,
  nearMisses: [
    { id: "n2", name: "○○ 국민임대", change: "지역을 은평구까지 넓히면", verdict: "ok" },
    { id: "n3", name: "○○ 장기전세", change: "자산 기준을 확인하면", verdict: "check" },
  ],
  error: { code: "E-503", at: "10월 19일 14:32" },
};
