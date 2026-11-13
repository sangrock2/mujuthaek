// 화면용 예시 데이터 (디자인 WebAlerts · MAlerts). 실제 값은 알림함 API (features/alerts/api.ts)

export type AlertType = "공고" | "혜택" | "공지";
export type AlertGroup = "오늘" | "어제" | "이번 주" | "이전";
export type AlertIcon = "home" | "clock" | "benefit" | "notice";

export type AlertItem = {
  id: string;
  group: AlertGroup;
  type: AlertType;
  icon: AlertIcon;
  kind: string;
  title: string;
  body: string;
  time: string;
  /** 모바일에서 줄여 쓰는 값 */
  short?: { title?: string; body?: string; time?: string };
  read: boolean;
  /** 누르면 갈 화면 (알림함 API의 linkPath). 없으면 이동하지 않아요 */
  linkPath?: string | null;
};

/** 받는 알림 요약(PC 오른쪽) */
export type AlertSetting = { label: string; on: boolean };

export type AlertsData = {
  items: AlertItem[];
  settings: AlertSetting[];
  quietHours: string;
};

export const alertsData: AlertsData = {
  items: [
    {
      id: "a1",
      group: "오늘",
      type: "공고",
      icon: "home",
      kind: "새 공고",
      title: "내 조건에 맞는 ○○지구 행복주택 공고가 나왔어요",
      body: "LH · 지원 가능 · 접수 10월 14일 ~ 31일",
      time: "2시간 전",
      read: false,
    },
    {
      id: "a2",
      group: "오늘",
      type: "공고",
      icon: "clock",
      kind: "마감 임박",
      title: "관심 공고 ○○ 행복주택 접수가 3일 남았어요",
      body: "10월 21일 마감 · 준비할 돈 960만 원",
      time: "5시간 전",
      read: false,
    },
    {
      id: "a3",
      group: "어제",
      type: "혜택",
      icon: "benefit",
      kind: "신청 시작",
      title: "청년 월세 지원 신청이 오늘 시작됐어요",
      body: "국토교통부 · 지원 가능 · 월 최대 20만 원",
      time: "어제 오전 9:00",
      short: { time: "어제 9:00" },
      read: false,
    },
    {
      id: "a4",
      group: "어제",
      type: "공고",
      icon: "home",
      kind: "정정 공고",
      title: "○○ 장기전세 접수 기간이 바뀌었어요",
      body: "GH · 10월 28일 마감 → 11월 4일 마감",
      time: "어제 오후 3:12",
      short: { body: "GH · 11월 4일 마감으로 연장", time: "어제 15:12" },
      read: true,
    },
    {
      id: "a5",
      group: "이번 주",
      type: "혜택",
      icon: "benefit",
      kind: "기준 변경",
      title: "기준중위소득이 바뀌어 판정 결과가 달라졌어요",
      body: "혜택 1개 · 공고 2곳을 다시 판정했어요",
      time: "3일 전",
      short: { title: "기준중위소득이 바뀌어 판정이 달라졌어요" },
      read: true,
    },
    {
      id: "a6",
      group: "이번 주",
      type: "공지",
      icon: "notice",
      kind: "공지",
      title: "경북·경남 지방 공사 공고도 이제 모아요",
      body: "수집하는 기관이 늘었어요",
      time: "5일 전",
      read: true,
    },
  ],
  settings: [
    { label: "새 공고", on: true },
    { label: "마감 D-3 · D-1", on: true },
    { label: "신청 시작", on: true },
    { label: "혜택 · 기준 변경", on: true },
    { label: "공지", on: false },
  ],
  quietHours: "밤 10시 ~ 아침 8시",
};
