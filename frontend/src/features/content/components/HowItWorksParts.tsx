"use client";

import {
  ArrowRight,
  Bell,
  CircleCheck,
  Download,
  FileText,
  ListChecks,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/shared/lib/cn";

// 「무주택자들은 어떻게 만들었나요」 내용. PC(WebHowItWorks) · 모바일(MHowItWorks)이 같이 써요.
// 숫자는 추출 평가 기록(정답표 23건, 같은 채점 기준)에 있는 값만, 측정 조건과 함께 적어요

type Variant = { web: boolean };

type Step = { icon: LucideIcon; title: string; desc: string; tag?: string };

const steps: Step[] = [
  {
    icon: Download,
    title: "공고 모으기",
    desc: "기관 게시판과 공공 API에서 주거 · 창업지원 공고와 정책을 정해진 시간마다 모아요. 정정 공고는 버전으로 남겨요.",
  },
  {
    icon: FileText,
    title: "첨부 읽기",
    desc: "PDF · HWP · 엑셀 · 그림 첨부를 글과 표로 바꾸고, 줄과 표 칸마다 번호를 붙여요. 그림 속 표는 두 번 따로 읽고 글자 인식 결과와 맞춰 봐요.",
  },
  {
    icon: Sparkles,
    title: "AI 섹션 담당",
    desc: "일정 · 자격 · 선정 · 서류를 AI 담당이 나눠 맡아요. 값마다 원문 위치(근거)를 붙여 넣고, 검증 결과를 받아 스스로 고쳐요.",
    tag: "AI",
  },
  {
    icon: ShieldCheck,
    title: "코드 검증",
    desc: "근거가 원문에 정말 있는지, 형식 · 금액이 맞는지 코드가 확인해요. 확실하지 않은 값은 게시하지 않고 사람 검수로 보내요.",
    tag: "코드",
  },
  {
    icon: ListChecks,
    title: "지원 가능 판정",
    desc: "내 조건과 공고의 자격 조건을 하나씩 비교해 지원 가능 · 확인 필요 · 지원 불가를 알려 드려요.",
  },
  {
    icon: Bell,
    title: "알림",
    desc: "조건에 맞는 새 공고, 관심 공고의 마감 · 정정 소식을 알려 드려요.",
  },
];

/** 핵심 원칙 두 가지 */
export function Principles({ web }: Variant) {
  const items = [
    {
      icon: CircleCheck,
      title: "틀린 값은 게시하지 않아요",
      desc: "확실하지 않으면 값을 지어내지 않고 「확인 필요」로 둬요. 사람이 원문을 보고 확인한 뒤에 보여 드려요.",
    },
    {
      icon: FileText,
      title: "모든 값에 원문 근거가 있어요",
      desc: "AI가 뽑은 값마다 원문의 어느 줄 · 어느 표 칸에서 왔는지 남겨요. 인용 글은 AI가 옮겨 적지 않고 코드가 원문에서 그대로 꺼내요.",
    },
  ];
  return (
    <section aria-label="핵심 원칙" className={cn("grid gap-3", web && "grid-cols-2")}>
      {items.map(({ title, desc, icon: Icon }) => (
        <div key={title} className="rounded-card bg-surface flex flex-col gap-2 p-5 lg:p-6">
          <h2 className="m-0 flex items-center gap-2 text-base font-extrabold lg:text-lg">
            <Icon size={18} className="text-brand-strong shrink-0" aria-hidden />
            {title}
          </h2>
          <p className="text-text-sub m-0 text-sm leading-relaxed lg:text-[15px]">{desc}</p>
        </div>
      ))}
    </section>
  );
}

/** 전체 흐름: PC는 3칸 × 2줄, 모바일은 세로 줄 */
export function FlowSteps({ web }: Variant) {
  return (
    <ol className={cn("m-0 list-none p-0", web ? "grid grid-cols-3 gap-3" : "flex flex-col gap-2")}>
      {steps.map((s, i) => {
        const Icon = s.icon;
        return (
          <li
            key={s.title}
            className={cn(
              "rounded-card bg-surface flex gap-3 p-4",
              web ? "flex-col lg:p-5" : "items-start",
            )}
          >
            <span className={cn("flex items-center gap-[10px]", !web && "flex-none self-start")}>
              <span className="rounded-pill bg-brand-soft text-brand-strong flex size-8 flex-none items-center justify-center">
                <Icon size={17} aria-hidden />
              </span>
              {web && <StepTitle step={s} n={i + 1} web />}
            </span>
            <span className={"flex min-w-0 flex-col gap-1.5"}>
              {!web && <StepTitle step={s} n={i + 1} web={false} />}
              <span className="text-text-body-long text-[15px] leading-[1.65]">{s.desc}</span>
              {s.title === "코드 검증" && (
                <span className="flex flex-wrap gap-[6px] pt-[2px]">
                  <span className="rounded-badge bg-ok-bg text-ok-text px-[8px] py-[3px] text-[13px] font-bold">
                    확실함 → 게시
                  </span>
                  <span className="rounded-badge bg-check-bg text-check-text px-[8px] py-[3px] text-[13px] font-bold">
                    확실하지 않음 → 확인 필요 · 사람 검수
                  </span>
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function StepTitle({ step, n, web }: { step: Step; n: number; web: boolean }) {
  return (
    <span className="flex flex-wrap items-center gap-[6px]">
      <span className="sr-only">{n}.</span>
      <span className={cn("tracking-title font-extrabold", web ? "text-[18px]" : "text-[17px]")}>
        {step.title}
      </span>
      {step.tag && (
        <span className="rounded-tag bg-neutral-bg text-neutral-text px-[6px] py-[1px] text-[12px] font-bold">
          {step.tag}
        </span>
      )}
    </span>
  );
}

const verificationSteps = [
  { title: "원문", detail: "줄 · 표 칸 번호" },
  { title: "AI 섹션 담당", detail: "일정 · 자격 · 선정 · 서류" },
  { title: "값과 근거 입력", detail: "원문 위치를 함께 기록" },
  { title: "코드 검증", detail: "근거 · 형식 · 금액" },
];

export function AgentLoop() {
  return (
    <figure className="rounded-card bg-surface m-0 flex flex-col gap-3 p-4 lg:p-6">
      <ol className="bg-fill rounded-card m-0 grid list-none grid-cols-2 gap-3 p-2.5 lg:grid-cols-4 lg:gap-5">
        {verificationSteps.map(({ title, detail }, index) => {
          const last = index === verificationSteps.length - 1;
          return (
            <li
              key={title}
              className={cn(
                "rounded-tile relative flex min-w-0 flex-col justify-center gap-1 px-3 py-2.5 text-center",
                last ? "bg-brand-soft text-brand-strong" : "bg-surface",
              )}
            >
              <strong className="text-sm">{title}</strong>
              <span className="text-text-sub text-xs leading-relaxed">{detail}</span>
              {!last && (
                <ArrowRight
                  size={14}
                  className="text-text-sub absolute top-1/2 -right-[17px] hidden -translate-y-1/2 lg:block"
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>
      <figcaption className="text-text-sub text-sm leading-relaxed">
        코드가 검증 결과를 돌려주면 AI 담당이 값을 고쳐요. 검증을 통과한 값은 게시하고, 확인이
        필요한 값은 사람이 원문을 다시 봐요.
      </figcaption>
    </figure>
  );
}

/* ---------- AI와 코드의 역할 ---------- */

const roles = [
  { work: "원문", ai: "읽고 판단해요", code: "줄 · 표 칸마다 번호를 붙인 문서로 만들어요" },
  {
    work: "공급 · 가격 표",
    ai: "각 열이 무슨 뜻인지만 답해요",
    code: "칸 값은 원문에서 그대로 옮겨요",
  },
  {
    work: "값 넣기",
    ai: "섹션별 형식에 맞춰 값과 근거 번호를 넣어요",
    code: "넣는 즉시 형식 · 근거를 검사하고, 인용 글은 원문에서 꺼내요",
  },
  {
    work: "검증",
    ai: "검증 결과를 보고 스스로 고쳐요",
    code: "차례마다 검증해 고칠 것 · 확인할 것을 돌려줘요",
  },
  { work: "게시", ai: "–", code: "확실한 값만 게시하고, 아니면 확인 필요로 보류해요" },
];

export function Roles({ web }: Variant) {
  if (!web) {
    return (
      <ul className="m-0 flex list-none flex-col gap-[10px] p-0">
        {roles.map((r) => (
          <li
            key={r.work}
            className="rounded-card bg-surface flex flex-col gap-[8px] px-[18px] py-[16px]"
          >
            <span className="text-[16px] font-extrabold">{r.work}</span>
            <span className="flex gap-[8px] text-[14px] leading-[1.55]">
              <span className="text-brand-strong w-[34px] flex-none font-bold">AI</span>
              <span>{r.ai}</span>
            </span>
            <span className="flex gap-[8px] text-[14px] leading-[1.55]">
              <span className="text-text-sub w-[34px] flex-none font-bold">코드</span>
              <span>{r.code}</span>
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div className="rounded-card bg-surface overflow-hidden">
      <table className="w-full border-collapse text-left text-[15px]">
        <thead>
          <tr className="bg-fill">
            <th scope="col" className="w-[160px] px-[24px] py-[14px] text-[14px] font-bold">
              일
            </th>
            <th scope="col" className="text-brand-strong px-[16px] py-[14px] text-[14px] font-bold">
              AI가 하는 일
            </th>
            <th scope="col" className="px-[16px] py-[14px] text-[14px] font-bold">
              코드가 하는 일
            </th>
          </tr>
        </thead>
        <tbody>
          {roles.map((r) => (
            <tr key={r.work} className="border-line-soft border-t border-solid">
              <th scope="row" className="px-[24px] py-[14px] font-bold">
                {r.work}
              </th>
              <td className="px-[16px] py-[14px] leading-[1.55]">{r.ai}</td>
              <td className="px-[16px] py-[14px] leading-[1.55]">{r.code}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- 확인 필요로 보내는 경우 ---------- */

const reviewCases = [
  "그림 속 표를 두 번 따로 읽었는데 숫자가 다르면, 그 행의 가격 · 수량",
  "보증금이 계약금 + 잔금과 맞지 않으면",
  "호실마다 센 모집 수를 더한 값이 공고 전체 모집 수보다 크면",
  "「소득 130% 초과」처럼 아래 한도가 붙어 자격으로 단정하기 어려우면",
  "AI 담당이 끝까지 마치지 못했거나, 원문에 있는데 넣지 못한 것이 남으면 그 섹션 전체",
];

export function ReviewCases({ web }: Variant) {
  return (
    <ul
      className={cn(
        "rounded-card bg-surface m-0 flex list-none flex-col gap-2 p-0",
        web ? "p-5" : "p-3",
      )}
    >
      {reviewCases.map((c) => (
        <li
          key={c}
          className="rounded-tile bg-fill flex items-start gap-2.5 px-3 py-2.5 text-sm leading-relaxed"
        >
          <span className="rounded-badge bg-check-bg text-check-text mt-[2px] flex-none px-[7px] py-[2px] text-[12px] font-bold">
            확인 필요
          </span>
          <span>{c}</span>
        </li>
      ))}
    </ul>
  );
}

/* ---------- 숫자: 처음 방식(V1) → 지금 방식(V2) ---------- */

const metrics = [
  {
    label: "재현율",
    help: "정답표 값 가운데 맞게 뽑은 비율",
    v1: 87.92,
    v2: 96.39,
  },
  {
    label: "검수 없이 게시",
    help: "정답표 값 가운데 사람 확인 없이 바로 게시된 맞는 값의 비율",
    v1: 73.79,
    v2: 95.72,
  },
];

function Bar({ value, tone, label }: { value: number; tone: "old" | "new"; label: string }) {
  return (
    <span className="flex items-center gap-[10px]">
      <span className="text-text-sub w-[40px] flex-none text-[13px] font-bold">{label}</span>
      <span className="bg-fill relative h-[12px] flex-1 overflow-hidden rounded-[6px]">
        <span
          className={cn(
            "absolute inset-y-0 left-0 rounded-[6px]",
            tone === "new" ? "bg-brand/70" : "bg-off",
          )}
          style={{ width: `${value}%` }}
        />
      </span>
      <span
        className={cn(
          "w-[64px] flex-none text-right text-[15px]",
          tone === "new" ? "text-brand-strong font-extrabold" : "text-text-sub font-bold",
        )}
      >
        {value.toFixed(2)}%
      </span>
    </span>
  );
}

export function Numbers({ web }: Variant) {
  return (
    <div className="flex flex-col gap-[12px]">
      <div className={cn("grid gap-[12px]", web ? "grid-cols-2" : "grid-cols-1")}>
        {metrics.map((m) => (
          <div
            key={m.label}
            className={cn(
              "rounded-card bg-surface flex flex-col gap-[10px]",
              web ? "px-[26px] py-[22px]" : "px-[18px] py-[18px]",
            )}
          >
            <span className="flex flex-col gap-[2px]">
              <span className="text-[17px] font-extrabold">{m.label}</span>
              <span className="text-text-sub text-[13px]">{m.help}</span>
            </span>
            <Bar value={m.v1} tone="old" label="처음" />
            <Bar value={m.v2} tone="new" label="지금" />
          </div>
        ))}
      </div>
      <dl className={cn("m-0 grid gap-[12px]", web ? "grid-cols-2" : "grid-cols-1")}>
        <div
          className={cn(
            "rounded-card bg-surface flex flex-col gap-[4px]",
            web ? "px-[26px] py-[22px]" : "px-[18px] py-[18px]",
          )}
        >
          <dt className="text-[17px] font-extrabold">자동 게시된 틀린 값</dt>
          <dd className="m-0 flex items-baseline gap-[8px]">
            <span className="text-text-sub text-[18px] font-bold">12개</span>
            <span className="text-text-tertiary" aria-hidden>
              →
            </span>
            <span className="sr-only">에서</span>
            <span className="text-brand-strong text-[28px] font-extrabold">0개</span>
          </dd>
        </div>
        <div
          className={cn(
            "rounded-card bg-surface flex flex-col gap-[4px]",
            web ? "px-[26px] py-[22px]" : "px-[18px] py-[18px]",
          )}
        >
          <dt className="text-[17px] font-extrabold">비용</dt>
          <dd className="m-0 flex flex-col gap-[2px]">
            <span className="text-[28px] font-extrabold">+17.4%</span>
            <span className="text-text-sub text-[13px]">
              같은 23건을 처리한 AI 비용 합계의 차이예요
            </span>
          </dd>
        </div>
      </dl>
      <p className="text-text-sub m-0 px-[4px] text-[13px] leading-[1.7]">
        <strong className="text-text">측정 조건</strong> · 공고 23건을 사람이 원문을 보고 만든
        정답표(값 3,155개)와 같은 채점 기준으로 대조했어요. 처음 방식(섹션마다 AI를 한 번 불러 큰
        결과를 받는 정해진 단계)은 2026년 11월 5~6일, 지금 방식(섹션 담당 에이전트)은 11월 10일에
        쟀어요. 처음 방식은 그 뒤 두 방식이 함께 쓰게 된 개선을 반영하지 않아, 지금 방식에 다소
        유리한 비교예요. 비용은 운영 조건으로 센 23건 합계예요. 재현율 목표(98%)에는 아직 못 미쳐서
        계속 고치고 있어요.
      </p>
    </div>
  );
}

/* ---------- 판정 ---------- */

const verdicts = [
  { badge: "지원 가능", tone: "bg-ok-bg text-ok-text", desc: "자격 조건을 모두 충족해요" },
  {
    badge: "확인 필요",
    tone: "bg-check-bg text-check-text",
    desc: "모르는 조건이 있어요. 무엇을 넣으면 정해지는지 함께 알려 드려요",
  },
  {
    badge: "지원 불가",
    tone: "bg-neutral-bg text-neutral-text",
    desc: "맞지 않는 조건이 있어요. 어떤 조건인지 알려 드려요",
  },
];

export function Verdicts({ web }: Variant) {
  return (
    <div
      className={cn(
        "rounded-card bg-surface flex flex-col gap-[14px]",
        web ? "px-[28px] py-[24px]" : "px-[18px] py-[18px]",
      )}
    >
      <ul className={cn("m-0 grid list-none gap-[10px] p-0", web ? "grid-cols-3" : "grid-cols-1")}>
        {verdicts.map((v) => (
          <li
            key={v.badge}
            className="rounded-tile bg-bg flex flex-col gap-[8px] px-[16px] py-[14px]"
          >
            <span
              className={cn(
                "rounded-badge self-start px-[9px] py-[4px] text-[13px] font-bold",
                v.tone,
              )}
            >
              {v.badge}
            </span>
            <span className="text-[15px] leading-[1.55]">{v.desc}</span>
          </li>
        ))}
      </ul>
      <p className="text-text-sub m-0 text-[14px] leading-[1.65]">
        판정에 쓰는 소득 · 자산은 정확한 금액 대신 구간으로만 보내고, 서버에 저장하지 않아요. 대출
        자격 확인처럼 정확한 금액이 필요한 화면도 넣은 값을 저장하지 않아요.
      </p>
    </div>
  );
}

/** 섹션 제목 */
export function SectionTitle({ title, sub, web }: { title: string; sub?: string } & Variant) {
  return (
    <div className={cn("flex flex-col gap-[4px]", !web && "px-[4px]")}>
      <h2 className={cn("tracking-title m-0 font-extrabold", web ? "text-[24px]" : "text-[20px]")}>
        {title}
      </h2>
      {sub && (
        <span className={cn("text-text-sub leading-[1.6]", web ? "text-[16px]" : "text-[14px]")}>
          {sub}
        </span>
      )}
    </div>
  );
}
