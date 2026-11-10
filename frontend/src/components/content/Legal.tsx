import Link from "next/link";
import { Segment } from "@/components/ui/Segment";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { LegalBlock, LegalSection, MobileLegalSection } from "@/mocks/content-legal";

/** PC 제목 줄 오른쪽 버전 선택 */
export function WebVersionSelect({ label, versions }: { label: string; versions: string[] }) {
  return (
    <label className="text-text-sub inline-flex items-center gap-[8px] text-[14px]">
      {label}
      <select className="bg-surface text-text min-h-[44px] rounded-sm border-0 px-[14px] text-[15px] font-semibold">
        {versions.map((v) => (
          <option key={v}>{v}</option>
        ))}
      </select>
    </label>
  );
}

/** PC 목차 */
export function WebLegalToc({ sections }: { sections: LegalSection[] }) {
  return (
    <nav
      aria-label="목차"
      className="rounded-card bg-surface box-content flex min-w-0 flex-col gap-[2px] p-[18px]"
      style={{ flex: "1 1 240px" }}
    >
      <span className="text-text-sub px-[10px] pt-[6px] pb-[8px] text-[14px] font-extrabold">
        목차
      </span>
      {sections.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          className={cn(
            "flex min-h-[40px] items-center rounded-[10px] px-[10px] text-[15px] no-underline",
            s.emphasis
              ? "bg-brand-soft text-brand-strong hover:text-brand-strong font-bold"
              : "text-text hover:text-text",
          )}
        >
          {s.toc}
        </a>
      ))}
    </nav>
  );
}

function Block({ block, mobile }: { block: LegalBlock; mobile?: boolean }) {
  switch (block.kind) {
    case "p":
      return <p className={cn("m-0", block.small && "text-[15px]")}>{block.text}</p>;
    case "ol":
      return (
        <ol className="m-0 flex list-decimal flex-col gap-[6px] pl-[22px]">
          {block.items.map((it) => (
            <li key={it}>{it}</li>
          ))}
        </ol>
      );
    case "table":
      // 모바일은 좁아서 표 대신 줄마다 카드로 (내용은 웹 표와 같아요)
      if (mobile) {
        return (
          <div className="flex flex-col gap-[8px]">
            {block.rows.map((r) => (
              <div
                key={r.label}
                className="bg-bg rounded-sm px-[14px] py-[12px] text-[14px] leading-[1.6]"
              >
                <strong className="text-text">{r.label}</strong>
                <br />
                {r.text}
                {r.strong && <strong className="text-brand-strong">{r.strong}</strong>}
                {r.when && (
                  <>
                    <br />
                    <span className="text-text-sub">
                      {block.head[2]} · {r.when}
                    </span>
                  </>
                )}
              </div>
            ))}
          </div>
        );
      }
      return (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse text-[15px] leading-[1.6]">
            <thead>
              <tr className="bg-bg text-text">
                {block.head.map((h, i) => (
                  <th
                    key={h}
                    scope="col"
                    className={cn(
                      "px-[14px] py-[12px] text-left",
                      i === 0 && "rounded-l-[12px]",
                      i === block.head.length - 1 && "rounded-r-[12px]",
                    )}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((r) => (
                <tr key={r.label}>
                  <td className="border-line-soft text-text border-b border-solid p-[14px] font-bold">
                    {r.label}
                  </td>
                  <td className="border-line-soft border-b border-solid p-[14px]">
                    {r.text}
                    {r.strong && <strong className="text-brand-strong">{r.strong}</strong>}
                  </td>
                  <td className="border-line-soft border-b border-solid p-[14px]">{r.when}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "contact":
      return (
        <dl className="bg-bg m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-[18px] gap-y-[6px] rounded-[18px] px-[22px] py-[18px] text-[15px]">
          {block.items.map((it) => (
            <div key={it.term} className="contents">
              <dt className="text-text-sub">{it.term}</dt>
              <dd className={cn("text-text m-0", it.strong && "font-bold")}>{it.desc}</dd>
            </div>
          ))}
        </dl>
      );
    case "link":
      return (
        <Link
          href={block.href}
          className="inline-flex min-h-[44px] items-center self-start text-[15px] font-bold no-underline"
        >
          {block.label}
        </Link>
      );
  }
}

const sectionGap = (s: LegalSection) =>
  s.blocks.some((b) => b.kind === "table")
    ? "gap-[12px]"
    : s.blocks.some((b) => b.kind === "contact")
      ? "gap-[10px]"
      : "gap-[8px]";

/** PC 본문 조항 */
export function WebLegalSection({ section }: { section: LegalSection }) {
  return (
    <section
      id={section.id}
      className={cn(
        "flex scroll-mt-[24px] flex-col",
        sectionGap(section),
        section.emphasis && "bg-brand-soft text-text rounded-[18px] px-[22px] py-[20px]",
      )}
    >
      <h2
        className={cn(
          "tracking-title m-0 text-[20px] font-extrabold",
          section.emphasis ? "text-brand-strong" : "text-text",
        )}
      >
        {section.title ?? section.toc}
      </h2>
      {section.blocks.map((b, i) => (
        <Block key={i} block={b} />
      ))}
    </section>
  );
}

/** PC 본문 카드 */
export function WebLegalArticle({ children }: { children: React.ReactNode }) {
  return (
    <article
      className="rounded-card-lg bg-surface text-text-body-long box-content flex min-w-0 flex-col gap-[30px] px-[40px] py-[36px] text-[16px] leading-[1.85]"
      style={{ flex: "999 1 600px" }}
    >
      {children}
    </article>
  );
}

export function WebLegalClosing({ children }: { children: React.ReactNode }) {
  return (
    <span className="border-line-soft text-text-sub border-t border-solid pt-[18px] text-[14px]">
      {children}
    </span>
  );
}

/** 모바일: 이용약관 / 개인정보처리방침 바꾸기 */
export function MLegalTabs({ current }: { current: "terms" | "privacy" }) {
  return (
    <Segment
      compact
      items={[
        { label: "이용약관", href: routes.terms, selected: current === "terms" },
        { label: "개인정보처리방침", href: routes.privacy, selected: current === "privacy" },
      ]}
      itemClassName="flex-1 justify-center min-h-[40px] leading-normal"
    />
  );
}

/** 모바일: 웹과 같은 조항(전체 본문)을 접고 펼쳐요. 처음 조항과 강조 조항은 펼쳐 둬요 */
export function MLegalSection({ section, open }: { section: LegalSection; open?: boolean }) {
  return (
    <details
      open={open || section.emphasis}
      className={cn(
        section.emphasis
          ? "bg-brand-soft rounded-tile px-[16px] pt-[6px] pb-[14px]"
          : "border-line-soft border-b border-solid pt-[6px] pb-[14px]",
      )}
    >
      <summary
        className={cn(
          "flex min-h-[44px] cursor-pointer items-center text-[16px] font-extrabold",
          section.emphasis ? "text-brand-strong" : "text-text",
        )}
      >
        {section.title ?? section.toc}
      </summary>
      <div className={cn("mt-[4px] flex flex-col gap-[8px]", section.emphasis && "text-text")}>
        {section.blocks.map((b, i) => (
          <Block key={i} block={b} mobile />
        ))}
      </div>
    </details>
  );
}

/** 모바일: 접고 펼치는 조항 (예전 짧은 본문) */
export function MLegalDetails({ section }: { section: MobileLegalSection }) {
  return (
    <details
      open={section.open}
      className={cn(
        section.emphasis
          ? "bg-brand-soft rounded-tile px-[16px] pt-[6px] pb-[14px]"
          : "border-line-soft border-b border-solid pt-[6px] pb-[14px]",
      )}
    >
      <summary
        className={cn(
          "flex min-h-[44px] cursor-pointer items-center text-[16px] font-extrabold",
          section.emphasis ? "text-brand-strong" : "text-text",
        )}
      >
        {section.title}
      </summary>
      {section.text && (
        <p className={cn("mx-0 mt-[4px] mb-0", section.emphasis && "text-text")}>{section.text}</p>
      )}
      {section.cards && (
        <div className="mt-[6px] flex flex-col gap-[8px]">
          {section.cards.map((c) => (
            <div
              key={c.label}
              className="bg-bg rounded-sm px-[14px] py-[12px] text-[14px] leading-[1.6]"
            >
              <strong className="text-text">{c.label}</strong>
              <br />
              {c.text}
              {c.strong && <strong className="text-brand-strong">{c.strong}</strong>}
            </div>
          ))}
        </div>
      )}
    </details>
  );
}

/** 모바일 약관 화면 바탕(흰색) */
export function MLegalMain({ children }: { children: React.ReactNode }) {
  return (
    <main className="text-text-body-long flex flex-1 flex-col gap-[14px] px-[20px] pt-[16px] pb-[32px] text-[15px] leading-[1.8]">
      {children}
    </main>
  );
}
