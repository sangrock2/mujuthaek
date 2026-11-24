import Link from "next/link";
import { ArrowRight, BriefcaseBusiness, ChevronRight, House } from "lucide-react";
import { routes } from "@/shared/lib/routes";

const destinations = [
  {
    title: "살 곳을 찾아요",
    detail: "청약·공공임대 · 주거 혜택",
    href: routes.home,
    icon: House,
    tone: "bg-brand-soft",
  },
  {
    title: "일할 곳을 찾아요",
    detail: "사업공간 · 창업 지원",
    href: routes.business,
    icon: BriefcaseBusiness,
    tone: "bg-fill",
  },
];

export function LandingIntro({
  start,
  signedIn,
}: {
  start: { href: string; label: string };
  signedIn: boolean;
}) {
  const label = start.href === routes.profile ? "조건 입력하고 시작하기" : start.label;
  return (
    <div className="bg-bg px-[16px] pt-[16px] pb-[28px] sm:px-[32px] sm:pt-[28px] sm:pb-[36px]">
      <div className="mx-auto flex max-w-[1136px] flex-col gap-[12px] lg:gap-[16px]">
        <section
          aria-labelledby="intro-title"
          className="rounded-card-lg border-line-soft bg-surface relative isolate overflow-hidden border px-[20px] py-[42px] text-center sm:px-[40px] lg:py-[98px]"
        >
          <div
            aria-hidden
            className="pointer-events-none absolute -inset-x-[20%] -top-[65%] -z-10 h-[115%] bg-[radial-gradient(ellipse_at_center,var(--color-brand-soft),transparent_67%)]"
          />
          <h1
            id="intro-title"
            className="tracking-h1 m-0 text-[clamp(1.9rem,5.2vw,4rem)] leading-[1.16] font-extrabold break-keep"
          >
            내 조건에 맞는
            <br />
            집과 혜택을 한 번에
          </h1>
          <p className="text-text-sub mx-auto mt-[16px] max-w-[540px] text-[15px] leading-[1.65] break-keep lg:mt-[20px] lg:text-[19px]">
            청약·공공임대 공고와 주거 지원 정책을 모아, 어디에 신청할 수 있는지 확인해 드려요.
          </p>
          <div className="mt-[23px] flex flex-col items-center gap-[9px] lg:mt-[31px]">
            <Link
              href={start.href}
              className="rounded-control bg-brand hover:bg-brand-strong flex min-h-[52px] w-full max-w-[290px] items-center justify-center gap-[8px] px-[18px] text-[16px] font-extrabold text-white no-underline hover:text-white lg:min-h-[58px] lg:text-[18px]"
            >
              {label}
              <ArrowRight size={19} aria-hidden />
            </Link>
            {!signedIn && (
              <span className="text-text-sub text-[13px]">로그인 없이 시작할 수 있어요</span>
            )}
          </div>
        </section>
        <nav
          aria-label="서비스 바로가기"
          className="mx-auto grid w-full max-w-[950px] gap-[8px] sm:grid-cols-2 lg:gap-[12px]"
        >
          {destinations.map(({ title, detail, href, icon: Icon, tone }) => (
            <Link
              key={href}
              href={href}
              className={`rounded-card text-text hover:text-brand-strong flex min-w-0 items-center gap-[12px] px-[15px] py-[13px] no-underline lg:min-h-[106px] lg:gap-[15px] lg:p-[20px] ${tone}`}
            >
              <span className="rounded-control bg-surface text-brand-strong flex size-[42px] shrink-0 items-center justify-center lg:size-[52px]">
                <Icon size={21} aria-hidden />
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                <strong className="text-[16px] lg:text-[20px]">{title}</strong>
                <span className="text-text-sub text-[13px]">{detail}</span>
              </span>
              <ChevronRight size={18} className="text-text-tertiary shrink-0" aria-hidden />
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}
