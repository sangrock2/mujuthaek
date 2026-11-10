import { Bell, Building, House, Store, User, Wallet, type LucideIcon } from "lucide-react";
import { routes, type Mode } from "@/lib/routes";

export type NavItem = { label: string; href: string; icon: LucideIcon };

// PC 주 메뉴
export const webMenu: Record<Mode, NavItem[]> = {
  home: [
    { label: "홈", href: routes.home, icon: House },
    { label: "내 혜택", href: routes.benefits, icon: Wallet },
    { label: "내 집", href: routes.homes, icon: Building },
  ],
  business: [
    { label: "공간 찾기", href: routes.business, icon: Store },
    { label: "사업 지원", href: routes.bizSupport, icon: Wallet },
  ],
};

// 모바일 하단 탭
export const mobileTabs: Record<Mode, NavItem[]> = {
  home: [...webMenu.home, { label: "내 정보", href: routes.me, icon: User }],
  business: [
    ...webMenu.business,
    { label: "알림", href: routes.alerts, icon: Bell },
    { label: "내 정보", href: routes.me, icon: User },
  ],
};

export const modeSegment = (mode: Mode) => [
  { label: "주거", href: routes.home, selected: mode === "home" },
  { label: "사업공간", href: routes.business, selected: mode === "business" },
];
