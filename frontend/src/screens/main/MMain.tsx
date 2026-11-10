"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight, CircleCheck, House, Lock, Wallet, type LucideIcon } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { VerdictBadge } from "@/components/ui/Badge";
import { useMainLanding } from "@/features/main/queries";
import { cn } from "@/lib/cn";
import { useSession } from "@/features/auth/session";
import { useStartLinks } from "@/features/main/start";
import { faqs, howSteps, trust } from "@/features/main/landing";
import { reportHref } from "@/features/me/tabs";
import { routes } from "@/lib/routes";

const eyebrow = "text-brand-strong text-[14px] font-bold";
const h2 = "tracking-h1 m-0 text-[26px] leading-[1.35] font-extrabold";
const footLink =
  "text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center text-[14px] no-underline";

const features = [
  {
    href: routes.benefits,
    title: "정부·지자체 주거 혜택",
    desc: "청년 월세 지원, 전세자금 대출처럼 받을 수 있는 정책과 금액",
  },
  { href: routes.homes, title: "청약·공공임대 공고", desc: "지원할 수 있는 곳과 내가 준비할 돈" },
  {
    href: routes.business,
    title: "사업공간 · 사업 지원",
    desc: "창업 공간, 공공 상가, 회의실과 창업 지원금·정책자금",
  },
];

const judgeSteps = [
  "조건마다 충족 · 확인 필요로 나눠요",
  "근거가 된 원문을 바로 보여줘요",
  "준비할 돈까지 계산해요",
];

const MOBILE_CONDITIONS = 2;

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
    <div className="bg-surface flex items-center gap-[14px] rounded-[20px] p-[18px]">
      <span className="rounded-control bg-brand-soft text-brand flex size-[44px] flex-none items-center justify-center">
        <Icon size={24} strokeWidth={1.8} aria-hidden />
      </span>
      <span className="flex flex-col gap-[2px]">
        <span className="text-text-sub text-[13px]">{label}</span>
        <span className="tracking-title text-[24px] font-extrabold">{value}</span>
      </span>
    </div>
  );
}

export function MMain() {
  // 로그인했으면 로그인 대신 이름 · 내 홈 (불러오는 동안은 숨겨요)
  const { data: session } = useSession();
  const links = useStartLinks();
  const { data } = useMainLanding();
  const { example, judgeExample } = data;
  // 「어떻게 판정하나요?」(#judge): PC 화면도 숨긴 채 같이 그려져(Responsive) 문서에서 먼저 나오는 id="judge"가 PC 쪽이라,
  // 브라우저 기본 이동은 모바일에서 숨은 칸을 찾아 움직이지 않아요. 모바일은 이 화면의 칸으로 직접 옮겨요
  const judgeRef = useRef<HTMLElement>(null);
  const showJudge = (behavior: ScrollBehavior) =>
    judgeRef.current?.scrollIntoView({ behavior, block: "start" });
  // 주소가 /#judge로 열렸을 때도 (PC 폭이면 PC 화면의 칸으로 브라우저가 이미 옮겨요)
  useEffect(() => {
    if (window.location.hash === "#judge" && !window.matchMedia("(min-width: 1024px)").matches) {
      judgeRef.current?.scrollIntoView({ block: "start" });
    }
  }, []);

  return (
    <div className="bg-surface text-text flex min-h-screen w-full flex-col">
      <header className="border-line-soft bg-surface sticky top-0 z-[2] flex h-[56px] items-center justify-between border-b border-solid pr-[8px] pl-[16px]">
        <Link
          href={routes.main}
          aria-label="무주택자들 홈"
          className="text-text hover:text-text inline-flex items-center gap-[8px] no-underline"
        >
          <Logo size={28} />
          <span className="tracking-logo text-[18px] font-extrabold">무주택자들</span>
        </Link>
        {session === null && (
          <Link
            href={routes.login}
            className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center px-[12px] text-[15px] font-semibold no-underline"
          >
            로그인
          </Link>
        )}
        {session && (
          <span className="flex items-center">
            <Link
              href={routes.me}
              className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center px-[8px] text-[15px] font-semibold no-underline"
            >
              {session.nickname}님
            </Link>
            <Link
              href={routes.home}
              className="text-brand-strong hover:text-brand-strong inline-flex min-h-[44px] items-center px-[8px] text-[15px] font-bold no-underline"
            >
              내 홈
            </Link>
          </span>
        )}
      </header>

      <main className="flex flex-1 flex-col">
        <section
          aria-label="소개"
          className="flex flex-col gap-[18px] px-[20px] pt-[36px] pb-[32px]"
        >
          <span className="rounded-pill bg-brand-soft text-brand-strong self-start px-[12px] py-[6px] text-[13px] font-bold">
            무주택자를 위한 집 · 혜택 찾기
          </span>
          <h1 className="tracking-logo m-0 text-[32px] leading-[1.3] font-extrabold">
            내 조건으로 받을 수 있는
            <br />
            집과 혜택을 한 번에
          </h1>
          <p className="text-text-sub m-0 text-[17px] leading-[1.65]">
            청약·공공임대 공고와 정부·지자체 주거 정책을 모아, 내가 지원할 수 있는지까지
            판정해드려요
          </p>
          <Link
            href={links.start.href}
            className="bg-brand mt-[6px] flex min-h-[58px] items-center justify-center gap-[8px] rounded-[16px] text-[18px] font-extrabold text-white no-underline hover:text-white"
          >
            {links.start.label}
            <ArrowRight size={20} strokeWidth={2.2} aria-hidden />
          </Link>
          <a
            href="#judge"
            onClick={(e) => {
              e.preventDefault();
              if (window.location.hash !== "#judge") window.history.pushState(null, "", "#judge");
              showJudge("smooth");
            }}
            className="bg-fill text-text hover:text-text flex min-h-[52px] items-center justify-center rounded-[16px] text-[16px] font-bold no-underline"
          >
            어떻게 판정하나요?
          </a>
          <div className="text-text-sub flex flex-wrap justify-center gap-x-[16px] gap-y-[6px] text-[14px]">
            {!session && (
              <span className="inline-flex items-center gap-[5px]">
                <CircleCheck size={16} className="text-brand" aria-hidden />
                가입 없이 바로
              </span>
            )}
            <span className="inline-flex items-center gap-[5px]">
              <Lock size={16} className="text-brand" aria-hidden />
              소득·자산은 저장 안 해요
            </span>
          </div>
        </section>

        <section
          aria-label="결과 화면 예시"
          className="rounded-card-lg bg-bg mx-[20px] flex flex-col gap-[12px] p-[20px]"
        >
          <div className="flex items-center justify-between">
            <span className="flex flex-wrap gap-[5px]">
              {example.conditions.slice(0, MOBILE_CONDITIONS).map((c) => (
                <span
                  key={c}
                  className="rounded-pill bg-surface text-text-sub px-[10px] py-[5px] text-[12px] font-semibold"
                >
                  {c}
                </span>
              ))}
            </span>
            <span className="text-text-sub text-[12px] font-semibold">예시</span>
          </div>
          <StatCard icon={House} label="지원 가능한 청약·공공임대" value={example.homesCount} />
          <StatCard icon={Wallet} label="받을 수 있는 혜택" value={example.benefitsSummary} />
        </section>

        <section
          aria-label="찾는 공간 고르기"
          className="flex flex-col gap-[10px] px-[20px] pt-[28px] pb-[8px]"
        >
          <Link
            href={links.homes}
            className="rounded-card bg-brand-soft text-text hover:text-text flex items-center gap-[14px] p-[20px] no-underline"
          >
            <span className="flex flex-1 flex-col gap-[3px]">
              <span className="tracking-title text-[19px] font-extrabold">살 곳을 찾아요</span>
              <span className="text-text-sub text-[14px]">청약 · 공공임대 · 정부 혜택</span>
            </span>
            <ArrowRight size={22} strokeWidth={2.2} className="text-brand" aria-hidden />
          </Link>
          <Link
            href={routes.business}
            className="rounded-card bg-bg text-text hover:text-text flex items-center gap-[14px] p-[20px] no-underline"
          >
            <span className="flex flex-1 flex-col gap-[3px]">
              <span className="tracking-title text-[19px] font-extrabold">일할 곳을 찾아요</span>
              <span className="text-text-sub text-[14px]">창업 공간 · 공공 상가 · 사업 지원</span>
            </span>
            <ArrowRight size={22} strokeWidth={2.2} className="text-text" aria-hidden />
          </Link>
        </section>

        <section
          id="features"
          aria-label="무엇을 찾아주나요"
          className="bg-bg mt-[32px] flex flex-col gap-[20px] px-[20px] py-[48px]"
        >
          <div className="flex flex-col gap-[8px]">
            <span className={eyebrow}>무엇을 찾아주나요</span>
            <h2 className={h2}>
              흩어져 있는 공고와 정책을
              <br />내 조건 하나로 모아요
            </h2>
          </div>
          {features.map((f) => (
            <Link
              key={f.title}
              href={f.href}
              className="bg-surface text-text hover:text-text flex flex-col gap-[6px] rounded-[22px] p-[20px] no-underline"
            >
              <span className="text-[18px] font-extrabold">{f.title}</span>
              <span className="text-text-sub text-[15px] leading-[1.6]">{f.desc}</span>
            </Link>
          ))}
        </section>

        <section
          ref={judgeRef}
          aria-label="자격 판정"
          className="flex scroll-mt-[56px] flex-col gap-[20px] px-[20px] py-[48px]"
        >
          <div className="flex flex-col gap-[8px]">
            <span className={eyebrow}>자격 판정</span>
            <h2 className={h2}>
              모아주기만 하지 않고,
              <br />내 자격을 판정해요
            </h2>
          </div>
          <div className="rounded-card border-line flex flex-col gap-[12px] border border-solid p-[20px] shadow-[0_10px_28px_rgba(25,31,40,0.07)]">
            <span className="flex gap-[6px]">
              <VerdictBadge verdict="ok" size="md" className="text-[12px]" />
              <span className="rounded-badge bg-neutral-bg text-neutral-text px-[9px] py-[4px] text-[12px] font-bold">
                {judgeExample.dday}
              </span>
            </span>
            <span className="tracking-title text-[20px] font-extrabold">{judgeExample.title}</span>
            {judgeExample.rows.map((r) =>
              r.verdict === "ok" ? (
                <span
                  key={r.label}
                  className="border-line-soft flex justify-between border-b border-solid py-[9px] text-[15px]"
                >
                  <span>{r.mobileLabel ?? r.label}</span>
                  <span className="text-brand-strong font-bold">충족</span>
                </span>
              ) : (
                <span
                  key={r.label}
                  className="flex items-center justify-between py-[6px] text-[15px]"
                >
                  <span>{r.mobileLabel ?? r.label}</span>
                  <VerdictBadge verdict="check" size="md" className="py-[3px]" />
                </span>
              ),
            )}
            <span className="border-line flex items-baseline justify-between border-t border-solid pt-[12px]">
              <span className="text-[15px] font-bold">내가 준비할 돈</span>
              <span className="text-[22px] font-extrabold">{judgeExample.prepareAmount}</span>
            </span>
            <div className="bg-bg flex flex-col gap-[4px] rounded-[14px] px-[14px] py-[12px]">
              <span className="text-text-sub text-[12px] font-bold">
                {judgeExample.quoteSource}
              </span>
              <span className="text-[14px] leading-[1.6]">{judgeExample.quote}</span>
            </div>
          </div>
          <ol className="m-0 flex list-none flex-col gap-[16px] p-0">
            {judgeSteps.map((s, i) => (
              <li key={s} className="flex gap-[12px]">
                <span className="bg-brand flex size-[30px] flex-none items-center justify-center rounded-[10px] text-[14px] font-extrabold text-white">
                  {i + 1}
                </span>
                <span className="text-[16px] leading-[1.55]">
                  <strong>{s}</strong>
                </span>
              </li>
            ))}
          </ol>
        </section>

        <section
          id="sources"
          aria-label="어디서 모으나요"
          className="bg-bg flex flex-col gap-[16px] px-[20px] py-[48px]"
        >
          <div className="flex flex-col gap-[8px]">
            <span className={eyebrow}>어디서 모으나요</span>
            <h2 className={h2}>
              공공기관 공고와 정책을
              <br />
              평일 매시간 확인해요
            </h2>
          </div>
          {data.sources.map((g) => (
            <div
              key={g.key}
              className="bg-surface flex flex-col gap-[10px] rounded-[22px] p-[18px]"
            >
              <span className="text-[16px] font-extrabold">{g.title}</span>
              <span className="flex flex-wrap gap-[6px]">
                {g.items.map((it) => (
                  <span
                    key={it}
                    className="rounded-pill bg-fill text-text px-[10px] py-[5px] text-[13px] font-semibold"
                  >
                    {it}
                  </span>
                ))}
              </span>
            </div>
          ))}
        </section>

        <section
          id="how"
          aria-label="이렇게 찾아요"
          className="flex flex-col gap-[14px] px-[20px] py-[48px]"
        >
          <div className="flex flex-col gap-[8px]">
            <span className={eyebrow}>이렇게 찾아요</span>
            <h2 className={h2}>세 단계면 끝나요</h2>
          </div>
          {howSteps.map(({ icon: Icon, title, desc }, i) => (
            <div key={title} className="bg-bg flex gap-[12px] rounded-[20px] p-[16px]">
              <span className="bg-brand flex size-[40px] flex-none items-center justify-center rounded-[12px] text-white">
                <Icon size={20} aria-hidden />
              </span>
              <span className="flex flex-col gap-[4px]">
                <span className="text-[16px] font-extrabold">
                  {i + 1}. {title}
                </span>
                <span className="text-text-sub text-[14px] leading-[1.6]">{desc}</span>
              </span>
            </div>
          ))}
        </section>

        <section
          aria-label="안심하고 쓰세요"
          className="bg-bg flex flex-col gap-[12px] px-[20px] py-[48px]"
        >
          <h2 className={h2}>안심하고 쓰세요</h2>
          {trust.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="bg-surface flex gap-[12px] rounded-[20px] p-[16px]">
              <Icon size={22} className="text-brand flex-none" aria-hidden />
              <span className="flex flex-col gap-[4px]">
                <span className="text-[16px] font-extrabold">{title}</span>
                <span className="text-text-sub text-[14px] leading-[1.6]">{desc}</span>
              </span>
            </div>
          ))}
        </section>

        <section
          id="faq"
          aria-label="자주 묻는 질문"
          className="flex flex-col gap-[10px] px-[20px] py-[48px]"
        >
          <h2 className="tracking-h1 m-0 mb-[8px] text-[26px] font-extrabold">자주 묻는 질문</h2>
          {faqs.map((f, i) => (
            <details key={f.q} open={i === 0} className="bg-bg rounded-[18px] px-[20px] py-[18px]">
              <summary className="min-h-[28px] cursor-pointer text-[16px] font-bold">{f.q}</summary>
              <p className="text-text-sub m-0 mt-[10px] text-[15px] leading-[1.7]">{f.a}</p>
            </details>
          ))}
          <Link
            href={routes.faq}
            className="inline-flex min-h-[44px] items-center self-center text-[15px] font-bold no-underline"
          >
            질문 더 보기
          </Link>
        </section>

        <section
          aria-label="시작하기"
          className="rounded-card-lg bg-brand-deep mx-[20px] mb-[40px] flex flex-col gap-[16px] px-[24px] py-[32px]"
        >
          <span className="tracking-h1 text-[24px] leading-[1.35] font-extrabold text-white">
            내 조건으로
            <br />
            지금 확인해보세요
          </span>
          <span className="text-brand-deep-text-2 text-[15px]">
            {session
              ? "받을 수 있는 집과 혜택부터 바로"
              : "가입 없이 바로, 받을 수 있는 집과 혜택부터"}
          </span>
          <Link
            href={links.start.href}
            className="rounded-control bg-surface text-brand-strong hover:text-brand-strong flex min-h-[56px] items-center justify-center text-[17px] font-extrabold no-underline"
          >
            {links.start.label}
          </Link>
        </section>
      </main>

      <footer className="border-line-soft flex flex-col gap-[8px] border-t border-solid px-[20px] pt-[24px] pb-[40px]">
        <nav aria-label="하단 링크" className="flex flex-wrap gap-x-[16px]">
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
            className={cn(footLink, "text-text hover:text-text font-bold")}
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
        <span className="text-text-sub text-[13px]">
          공고·정책 정보는 각 기관의 원문을 기준으로 해요
        </span>
      </footer>
    </div>
  );
}
