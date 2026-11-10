"use client";

import { reportHref } from "@/features/me/tabs";
import Link from "next/link";
import {
  ArrowRight,
  BriefcaseBusiness,
  Building,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  FileText,
  House,
  Landmark,
  Lock,
  Sparkles,
  Store,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { VerdictBadge } from "@/components/ui/Badge";
import { useMainLanding } from "@/features/main/queries";
import { cn } from "@/lib/cn";
import { useSession } from "@/features/auth/session";
import { useStartLinks } from "@/features/main/start";
import { faqs, howSteps, trust } from "@/features/main/landing";
import { routes } from "@/lib/routes";
import type { MainSourceGroup } from "@/mocks/main";

const wrap = "mx-auto box-border w-full max-w-[1200px] px-[32px]";
const eyebrow = "text-brand-strong text-[16px] font-bold";
const h2 = "tracking-h1 m-0 text-[42px] leading-[1.3] font-extrabold";
const navLink =
  "text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center px-[12px] text-[15px] font-medium no-underline";
const footLink =
  "text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center text-[14px] no-underline";

const features: { href: string; icon: LucideIcon; title: string; desc: string; cta: string }[] = [
  {
    href: routes.benefits,
    icon: Landmark,
    title: "정부·지자체 주거 혜택",
    desc: "청년 월세 지원, 전세자금 대출, 이사비 지원처럼 내가 받을 수 있는 정책과 금액",
    cta: "내 혜택 보기",
  },
  {
    href: routes.homes,
    icon: Building,
    title: "청약·공공임대 공고",
    desc: "LH와 지방 공사, 청약홈 공고 중 내가 지원할 수 있는 곳과 준비할 돈",
    cta: "내 집 보기",
  },
  {
    href: routes.business,
    icon: Store,
    title: "사업공간 · 사업 지원",
    desc: "창업 공간, 공공 상가, 회의실과 창업 지원금·정책자금",
    cta: "사업공간 보기",
  },
];

const judgeSteps = [
  {
    title: "조건마다 충족 · 확인 필요로 나눠요",
    desc: "나이, 소득, 무주택 같은 조건을 하나씩 판정해요",
  },
  {
    title: "근거가 된 원문을 바로 보여줘요",
    desc: "공고문의 어느 문장으로 판정했는지 확인할 수 있어요",
  },
  {
    title: "준비할 돈까지 계산해요",
    desc: "보증금에서 받을 수 있는 대출을 빼고, 마련할 돈을 알려드려요",
  },
];

const sourceIcon: Record<MainSourceGroup["key"], LucideIcon> = {
  homes: House,
  policy: Landmark,
  business: BriefcaseBusiness,
};

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="bg-surface shadow-float flex items-center gap-[16px] rounded-[22px] px-[24px] py-[22px]">
      <span className="rounded-control bg-brand-soft text-brand flex size-[48px] flex-none items-center justify-center">
        <Icon size={26} strokeWidth={1.8} aria-hidden />
      </span>
      <span className="flex flex-1 flex-col gap-[2px]">
        <span className="text-text-sub text-[14px]">{label}</span>
        <span className="tracking-title text-[28px] font-extrabold">{value}</span>
      </span>
      <ChevronRight size={22} className="text-text-tertiary" aria-hidden />
    </div>
  );
}

export function WebMain() {
  // 로그인했으면 로그인 대신 이름 · 내 홈 (불러오는 동안은 둘 다 숨겨요)
  const { data: session } = useSession();
  const links = useStartLinks();
  const { data } = useMainLanding();
  const { example, judgeExample } = data;

  return (
    <div className="bg-surface text-text flex min-h-screen w-full flex-col">
      <header className="border-line-soft bg-surface sticky top-0 z-20 border-b border-solid">
        <div
          className={cn(
            wrap,
            "flex min-h-[68px] flex-wrap items-center justify-between gap-x-[32px] gap-y-[12px]",
          )}
        >
          <div className="flex flex-wrap items-center gap-x-[40px] gap-y-[12px]">
            <Link
              href={routes.main}
              aria-label="무주택자들 홈"
              className="text-text hover:text-text inline-flex items-center gap-[10px] no-underline"
            >
              <Logo size={32} />
              <span className="tracking-logo text-[21px] font-extrabold">무주택자들</span>
            </Link>
            <nav aria-label="소개 메뉴" className="flex flex-wrap gap-[4px]">
              <a href="#features" className={navLink}>
                무엇을 찾아주나요
              </a>
              <a href="#how" className={navLink}>
                이렇게 찾아요
              </a>
              <a href="#sources" className={navLink}>
                어디서 모으나요
              </a>
              <a href="#faq" className={navLink}>
                자주 묻는 질문
              </a>
            </nav>
          </div>
          <div className="flex items-center gap-[8px]">
            {session ? (
              <Link href={routes.me} className={navLink}>
                {session.nickname}님
              </Link>
            ) : (
              session === null && (
                <Link href={routes.login} className={navLink}>
                  로그인
                </Link>
              )
            )}
            <Link
              href={session ? routes.home : routes.profile}
              className="bg-brand inline-flex min-h-[44px] items-center rounded-sm px-[18px] text-[15px] font-bold text-white no-underline hover:text-white"
            >
              {session ? "내 홈" : "시작하기"}
            </Link>
          </div>
        </div>
      </header>

      <main className="flex flex-1 flex-col">
        <section
          aria-label="소개"
          className={cn(wrap, "flex flex-wrap items-center gap-[56px] pt-[88px] pb-[64px]")}
        >
          <div className="flex min-w-0 flex-col gap-[24px]" style={{ flex: "999 1 480px" }}>
            <span className="rounded-pill bg-brand-soft text-brand-strong inline-flex items-center gap-[6px] self-start px-[14px] py-[7px] text-[14px] font-bold">
              <Sparkles size={16} aria-hidden />
              무주택자를 위한 집 · 혜택 찾기
            </span>
            <h1 className="tracking-h1 m-0 text-[58px] leading-[1.22] font-extrabold">
              내 조건으로 받을 수 있는
              <br />
              집과 혜택을 한 번에
            </h1>
            <p className="text-text-sub m-0 text-[20px] leading-[1.65]">
              청약·공공임대 공고와 정부·지자체 주거 정책을 모아,
              <br />
              내가 지원할 수 있는지까지 판정해드려요
            </p>
            <div className="mt-[8px] flex flex-wrap gap-[10px]">
              <Link
                href={links.start.href}
                className="rounded-control bg-brand inline-flex min-h-[60px] items-center gap-[8px] px-[26px] text-[18px] font-bold text-white no-underline hover:text-white"
              >
                {links.start.label}
                <ArrowRight size={20} strokeWidth={2.2} aria-hidden />
              </Link>
              <a
                href="#judge"
                className="rounded-control bg-fill text-text hover:text-text inline-flex min-h-[60px] items-center px-[24px] text-[18px] font-semibold no-underline"
              >
                어떻게 판정하나요?
              </a>
            </div>
            <div className="text-text-sub flex flex-wrap gap-x-[20px] gap-y-[8px] text-[15px]">
              {!session && (
                <span className="inline-flex items-center gap-[6px]">
                  <CircleCheck size={18} className="text-brand" aria-hidden />
                  가입 없이 바로
                </span>
              )}
              <span className="inline-flex items-center gap-[6px]">
                <Lock size={18} className="text-brand" aria-hidden />
                소득·자산은 저장하지 않아요
              </span>
            </div>
          </div>

          <div
            aria-label="결과 화면 예시"
            className="bg-bg flex min-w-0 flex-col gap-[14px] rounded-[32px] p-[28px]"
            style={{ flex: "1 1 420px" }}
          >
            <div className="flex items-center justify-between">
              <div className="flex flex-wrap gap-[6px]">
                {example.conditions.map((c) => (
                  <span
                    key={c}
                    className="rounded-pill bg-surface text-text-sub px-[12px] py-[6px] text-[13px] font-semibold"
                  >
                    {c}
                  </span>
                ))}
              </div>
              <span className="text-text-sub text-[12px] font-semibold">예시</span>
            </div>
            <StatCard icon={House} label="지원 가능한 청약·공공임대" value={example.homesCount} />
            <StatCard icon={Wallet} label="받을 수 있는 혜택" value={example.benefitsSummary} />
            <div className="bg-surface shadow-float flex flex-col gap-[12px] rounded-[22px] px-[24px] py-[18px]">
              <span className="text-[14px] font-bold">이번 주 새 소식</span>
              {example.news.map((n) => (
                <div key={n.id} className="flex items-center justify-between gap-[10px]">
                  <span className="flex flex-col gap-[2px]">
                    <span className="text-text-tertiary text-[12px]">{n.meta}</span>
                    <span className="text-[15px] font-semibold">{n.title}</span>
                  </span>
                  <VerdictBadge verdict={n.verdict} size="md" className="flex-none text-[12px]" />
                </div>
              ))}
            </div>
          </div>
        </section>

        <section aria-label="찾는 공간 고르기" className={cn(wrap, "pb-[96px]")}>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-[16px]">
            <Link
              href={links.homes}
              className="rounded-card-lg bg-brand-soft text-text hover:text-text flex items-center gap-[20px] px-[32px] py-[30px] no-underline"
            >
              <span className="bg-surface text-brand flex size-[64px] flex-none items-center justify-center rounded-[20px]">
                <House size={32} strokeWidth={1.8} aria-hidden />
              </span>
              <span className="flex flex-1 flex-col gap-[4px]">
                <span className="tracking-title text-[24px] font-extrabold">살 곳을 찾아요</span>
                <span className="text-text-sub text-[16px]">청약 · 공공임대 · 정부 혜택</span>
              </span>
              <ArrowRight size={26} strokeWidth={2.2} className="text-brand" aria-hidden />
            </Link>
            <Link
              href={routes.business}
              className="rounded-card-lg bg-bg text-text hover:text-text flex items-center gap-[20px] px-[32px] py-[30px] no-underline"
            >
              <span className="bg-surface text-text flex size-[64px] flex-none items-center justify-center rounded-[20px]">
                <BriefcaseBusiness size={32} strokeWidth={1.8} aria-hidden />
              </span>
              <span className="flex flex-1 flex-col gap-[4px]">
                <span className="tracking-title text-[24px] font-extrabold">일할 곳을 찾아요</span>
                <span className="text-text-sub text-[16px]">창업 공간 · 공공 상가 · 사업 지원</span>
              </span>
              <ArrowRight size={26} strokeWidth={2.2} className="text-text" aria-hidden />
            </Link>
          </div>
        </section>

        <section id="features" aria-label="무엇을 찾아주나요" className="bg-bg">
          <div className={cn(wrap, "flex flex-col gap-[40px] py-[104px]")}>
            <div className="flex flex-col gap-[12px]">
              <span className={eyebrow}>무엇을 찾아주나요</span>
              <h2 className={h2}>
                흩어져 있는 공고와 정책을
                <br />내 조건 하나로 모아요
              </h2>
            </div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(250px,1fr))] gap-[16px]">
              {features.map(({ href, icon: Icon, title, desc, cta }) => (
                <Link
                  key={title}
                  href={href}
                  className="rounded-card-lg bg-surface text-text hover:text-text flex flex-col gap-[14px] px-[28px] py-[30px] no-underline"
                >
                  <span className="rounded-tile bg-brand-soft text-brand flex size-[52px] items-center justify-center">
                    <Icon size={28} strokeWidth={1.8} aria-hidden />
                  </span>
                  <span className="tracking-title text-[21px] font-extrabold">{title}</span>
                  <span className="text-text-sub text-[16px] leading-[1.65]">{desc}</span>
                  <span className="text-brand-strong mt-auto inline-flex items-center gap-[2px] pt-[8px] text-[15px] font-bold">
                    {cta}
                    <ChevronRight size={18} strokeWidth={2.2} aria-hidden />
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </section>

        <section
          id="judge"
          aria-label="자격 판정"
          className={cn(wrap, "flex flex-wrap items-center gap-[64px] py-[112px]")}
        >
          <div className="flex min-w-0 flex-col gap-[28px]" style={{ flex: "999 1 440px" }}>
            <div className="flex flex-col gap-[12px]">
              <span className={eyebrow}>자격 판정</span>
              <h2 className={h2}>
                모아주기만 하지 않고,
                <br />내 자격을 판정해요
              </h2>
            </div>
            <ol className="m-0 flex list-none flex-col gap-[22px] p-0">
              {judgeSteps.map((s, i) => (
                <li key={s.title} className="flex gap-[16px]">
                  <span className="bg-brand flex size-[36px] flex-none items-center justify-center rounded-sm text-[16px] font-extrabold text-white">
                    {i + 1}
                  </span>
                  <span className="flex flex-col gap-[4px]">
                    <span className="text-[20px] font-bold">{s.title}</span>
                    <span className="text-text-sub text-[16px] leading-[1.6]">{s.desc}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <div
            aria-label="판정 화면 예시"
            className="rounded-card-lg border-line bg-surface flex min-w-0 flex-col gap-[16px] border border-solid p-[28px] shadow-[0_16px_40px_rgba(25,31,40,0.08)]"
            style={{ flex: "1 1 420px" }}
          >
            <div className="flex items-center justify-between">
              <div className="flex gap-[6px]">
                <VerdictBadge verdict="ok" size="lg" />
                <span className="rounded-badge bg-neutral-bg text-neutral-text px-[10px] py-[5px] text-[13px] font-bold">
                  {judgeExample.dday}
                </span>
              </div>
              <span className="text-text-tertiary text-[12px] font-semibold">예시</span>
            </div>
            <div className="flex flex-col gap-[4px]">
              <span className="tracking-title text-[23px] font-extrabold">
                {judgeExample.title}
              </span>
              <span className="text-text-tertiary text-[15px]">{judgeExample.meta}</span>
            </div>
            <div className="flex flex-col">
              {judgeExample.rows.map((r, i, list) => (
                <div
                  key={r.label}
                  className={cn(
                    "flex items-center justify-between py-[12px]",
                    i < list.length - 1 && "border-line-soft border-b border-solid",
                  )}
                >
                  <span className="text-[16px]">{r.label}</span>
                  {r.verdict === "ok" ? (
                    <span className="text-brand-strong inline-flex items-center gap-[6px] text-[15px] font-bold">
                      <CircleCheck size={20} aria-hidden />
                      충족
                    </span>
                  ) : (
                    <span className="rounded-badge bg-check-bg text-check-text inline-flex items-center gap-[6px] px-[10px] py-[4px] text-[14px] font-bold">
                      <CircleAlert size={18} aria-hidden />
                      확인 필요
                    </span>
                  )}
                </div>
              ))}
            </div>
            <div className="rounded-tile bg-bg flex gap-[10px] px-[16px] py-[14px]">
              <FileText
                size={20}
                strokeWidth={1.8}
                className="text-text-sub mt-px flex-none"
                aria-hidden
              />
              <span className="flex flex-col gap-[2px]">
                <span className="text-text-sub text-[13px] font-bold">
                  {judgeExample.quoteSource}
                </span>
                <span className="text-text-sub text-[14px] leading-[1.55]">
                  {judgeExample.quote}
                </span>
              </span>
            </div>
            <div className="border-line flex items-baseline justify-between border-t border-solid pt-[16px]">
              <span className="text-[16px] font-bold">내가 준비할 돈</span>
              <span className="tracking-title text-[26px] font-extrabold">
                {judgeExample.prepareAmount}
              </span>
            </div>
          </div>
        </section>

        <section id="how" aria-label="이렇게 찾아요" className="bg-bg">
          <div className={cn(wrap, "flex flex-col gap-[40px] py-[104px]")}>
            <div className="flex flex-col gap-[12px]">
              <span className={eyebrow}>이렇게 찾아요</span>
              <h2 className="tracking-h1 m-0 text-[42px] font-extrabold">
                조건만 알려주면 나머지는 저희가
              </h2>
            </div>
            <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-[16px] p-0">
              {howSteps.map(({ icon: Icon, title, desc }, i) => (
                <li
                  key={title}
                  className="rounded-card-lg bg-surface flex flex-col gap-[16px] px-[30px] py-[32px]"
                >
                  <span className="flex items-center justify-between">
                    <span className="text-brand text-[15px] font-extrabold">STEP {i + 1}</span>
                    <span className="rounded-tile bg-bg text-text flex size-[48px] items-center justify-center">
                      <Icon size={26} strokeWidth={1.8} aria-hidden />
                    </span>
                  </span>
                  <span className="tracking-title text-[22px] font-extrabold">{title}</span>
                  <span className="text-text-sub text-[16px] leading-[1.65]">{desc}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section
          id="sources"
          aria-label="어디서 모으나요"
          className={cn(wrap, "flex flex-col gap-[40px] py-[112px]")}
        >
          <div className="flex flex-wrap items-end justify-between gap-[16px]">
            <div className="flex flex-col gap-[12px]">
              <span className={eyebrow}>어디서 모으나요</span>
              <h2 className={h2}>
                공공기관 공고와 정책을
                <br />
                평일 매시간 확인해요
              </h2>
            </div>
            <span className="text-text-sub text-[16px]">원문 링크를 항상 함께 보여드려요</span>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-[16px]">
            {data.sources.map((g) => {
              const Icon = sourceIcon[g.key];
              return (
                <div
                  key={g.key}
                  className="rounded-card-lg border-line flex flex-col gap-[18px] border border-solid p-[28px]"
                >
                  <span className="flex items-center gap-[12px]">
                    <span className="rounded-control bg-brand-soft text-brand flex size-[44px] items-center justify-center">
                      <Icon size={24} strokeWidth={1.8} aria-hidden />
                    </span>
                    <h3 className="m-0 text-[19px] font-extrabold">{g.title}</h3>
                  </span>
                  <div className="flex flex-wrap gap-[6px]">
                    {g.items.map((it) => (
                      <span
                        key={it}
                        className="bg-fill text-text-sub rounded-[10px] px-[12px] py-[7px] text-[14px] font-semibold"
                      >
                        {it}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section aria-label="안심하고 쓰세요" className="bg-bg">
          <div
            className={cn(
              wrap,
              "grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-[40px] py-[88px]",
            )}
          >
            {trust.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="flex flex-col gap-[12px]">
                <span className="rounded-tile bg-surface text-brand flex size-[48px] items-center justify-center">
                  <Icon size={26} strokeWidth={1.8} aria-hidden />
                </span>
                <span className="tracking-title text-[21px] font-extrabold">{title}</span>
                <span className="text-text-sub text-[16px] leading-[1.65]">{desc}</span>
              </div>
            ))}
          </div>
        </section>

        <section
          id="faq"
          aria-label="자주 묻는 질문"
          className="mx-auto box-border flex w-full max-w-[880px] flex-col gap-[12px] px-[32px] py-[112px]"
        >
          <h2 className="tracking-h1 m-0 mb-[20px] text-center text-[42px] font-extrabold">
            자주 묻는 질문
          </h2>
          {faqs.map((f, i) => (
            <details
              key={f.q}
              open={i === 0}
              className="group bg-bg rounded-[20px] px-[26px] py-[22px]"
            >
              <summary className="flex min-h-[32px] cursor-pointer list-none items-center justify-between gap-[12px] text-[18px] font-bold [&::-webkit-details-marker]:hidden">
                {f.q}
                <ChevronRight
                  size={22}
                  className="text-text-sub transition-transform group-open:rotate-90"
                  aria-hidden
                />
              </summary>
              <p className="text-text-sub m-0 mt-[12px] text-[16px] leading-[1.7]">{f.a}</p>
            </details>
          ))}
        </section>

        <section aria-label="시작하기" className={cn(wrap, "pb-[112px]")}>
          <div className="bg-brand-deep flex flex-wrap items-center justify-between gap-[28px] rounded-[36px] px-[56px] py-[64px]">
            <div className="flex flex-col gap-[10px]">
              <span className="tracking-h1 text-[36px] font-extrabold text-white">
                내 조건으로 지금 확인해보세요
              </span>
              <span className="text-brand-deep-text-2 text-[18px]">
                {session
                  ? "받을 수 있는 집과 혜택부터 바로"
                  : "가입 없이 바로, 받을 수 있는 집과 혜택부터"}
              </span>
            </div>
            <Link
              href={links.start.href}
              className="rounded-control bg-surface text-brand-strong hover:text-brand-strong inline-flex min-h-[60px] items-center gap-[8px] px-[28px] text-[18px] font-extrabold no-underline"
            >
              {links.start.label}
              <ArrowRight size={20} strokeWidth={2.2} aria-hidden />
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-line-soft bg-surface border-t border-solid">
        <div className={cn(wrap, "flex flex-wrap justify-between gap-[24px] pt-[40px] pb-[56px]")}>
          <div className="flex flex-col gap-[10px]">
            <span className="inline-flex items-center gap-[8px]">
              <Logo size={24} />
              <span className="tracking-h1 text-[17px] font-extrabold">무주택자들</span>
            </span>
            <span className="text-text-tertiary text-[14px]">
              공고·정책 정보는 각 기관의 원문을 기준으로 해요
            </span>
          </div>
          <nav aria-label="하단 링크" className="flex flex-wrap gap-x-[20px] gap-y-[4px]">
            <Link href={routes.announcements} className={footLink}>
              공지사항
            </Link>
            <Link href={routes.faq} className={footLink}>
              자주 묻는 질문
            </Link>
            <Link href={routes.terms} className={footLink}>
              이용약관
            </Link>
            <Link
              href={routes.privacy}
              className="text-text hover:text-text inline-flex min-h-[44px] items-center text-[14px] font-bold no-underline"
            >
              개인정보처리방침
            </Link>
            <a href="#sources" className={footLink}>
              데이터 출처
            </a>
            <Link href={reportHref({ from: "소개 화면" })} className={footLink}>
              제보하기
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
