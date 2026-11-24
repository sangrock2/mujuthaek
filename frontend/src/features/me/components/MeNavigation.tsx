import Link from "next/link";
import {
  Bell,
  BriefcaseBusiness,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  FileText,
  Heart,
  History,
  LayoutGrid,
  Megaphone,
  Shield,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import type { MeTab } from "@/features/me/tabs";

export type MeDestination = MeTab | "overview";

type MenuItem = { label: string; icon: LucideIcon } & (
  { tab: MeDestination; href?: never } | { href: string; tab?: never }
);

export const meTitles: Record<MeDestination, string> = {
  overview: "마이페이지",
  conditions: "내 조건",
  favorites: "관심 공고",
  preparations: "신청 준비함",
  interests: "관심 조건",
  notifications: "알림 설정",
  privacy: "개인정보 설정",
  reports: "제보하기",
};

const overview: MenuItem = { label: meTitles.overview, icon: LayoutGrid, tab: "overview" };
const groups: { title: string; items: MenuItem[] }[] = [
  {
    title: "내 청약·공고",
    items: [
      { label: meTitles.conditions, icon: UserRound, tab: "conditions" },
      { label: meTitles.favorites, icon: Heart, tab: "favorites" },
      { label: meTitles.interests, icon: SlidersHorizontal, tab: "interests" },
      { label: meTitles.preparations, icon: ClipboardList, tab: "preparations" },
    ],
  },
  {
    title: "설정",
    items: [
      { label: meTitles.notifications, icon: Bell, tab: "notifications" },
      { label: meTitles.privacy, icon: Shield, tab: "privacy" },
    ],
  },
  {
    title: "지원·안내",
    items: [
      { label: meTitles.reports, icon: Megaphone, tab: "reports" },
      { label: "사업 정보", icon: BriefcaseBusiness, href: routes.bizOnboarding },
      { label: "공지사항", icon: FileText, href: routes.announcements },
      { label: "자주 묻는 질문", icon: CircleHelp, href: routes.faq },
      { label: "무주택자들은 어떻게 만들었나요", icon: Sparkles, href: routes.howItWorks },
    ],
  },
  {
    title: "약관·정책",
    items: [
      { label: "이용약관", icon: FileText, href: routes.terms },
      { label: "개인정보처리방침", icon: Shield, href: routes.privacy },
      { label: "약관·정책 이력", icon: History, href: routes.legal },
    ],
  },
];

export function meTabHref(tab: MeDestination, mobile = false) {
  if (tab === "overview") return routes.me;
  return mobile ? `${routes.me}/${tab}` : `${routes.me}?tab=${tab}`;
}

export function MeNavigation({
  mobile = false,
  current,
  onSelect,
  favorites,
  replies,
}: {
  mobile?: boolean;
  current?: MeDestination;
  onSelect?: (tab: MeDestination) => void;
  favorites?: number;
  replies: number;
}) {
  function renderItem(item: MenuItem) {
    const tab = item.tab;
    const selected = item.tab !== undefined && item.tab === current;
    const Icon = item.icon;
    const badge =
      item.tab === "favorites"
        ? favorites
        : item.tab === "reports" && replies
          ? `답변 ${replies}`
          : null;
    return (
      <Link
        key={item.label}
        href={tab ? meTabHref(tab, mobile) : (item.href ?? routes.me)}
        aria-current={selected ? "page" : undefined}
        onNavigate={
          tab && onSelect
            ? (event) => {
                event.preventDefault();
                onSelect(tab);
              }
            : undefined
        }
        className={cn(
          "rounded-control text-text hover:text-brand-strong flex min-h-[44px] items-center gap-[10px] px-[11px] py-[7px] text-[14px] font-semibold no-underline",
          selected ? "bg-brand-soft text-brand-strong font-extrabold" : "hover:bg-fill",
          mobile && "min-h-[48px] text-[15px]",
        )}
      >
        <Icon
          size={18}
          className={selected ? "shrink-0" : "text-text-tertiary shrink-0"}
          aria-hidden
        />
        <span className="min-w-0 flex-1">{item.label}</span>
        {badge != null && (
          <span className="rounded-pill bg-fill text-text-sub px-[7px] py-[2px] text-[12px] font-bold tabular-nums">
            {badge}
          </span>
        )}
        {mobile && <ChevronRight size={15} className="text-text-tertiary shrink-0" aria-hidden />}
      </Link>
    );
  }

  return (
    <nav
      aria-label="내 정보 메뉴"
      className={cn(
        "flex flex-col gap-[12px]",
        !mobile && "rounded-card border-line-soft bg-surface gap-[8px] border p-[8px]",
      )}
    >
      {!mobile && renderItem(overview)}
      {groups.map((group, index) => (
        <div
          key={group.title}
          className={cn(
            mobile
              ? "rounded-card border-line-soft bg-surface border p-[8px]"
              : index > 0 && "border-line-soft border-t pt-[7px]",
          )}
        >
          <h2 className="text-text-sub px-[11px] pt-[6px] pb-[3px] text-[12px] font-bold">
            {group.title}
          </h2>
          {group.items.map(renderItem)}
        </div>
      ))}
    </nav>
  );
}
