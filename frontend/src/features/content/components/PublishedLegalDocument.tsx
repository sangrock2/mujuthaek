import Link from "next/link";
import { LEGAL_CONTACT, type LegalDocument } from "@/features/content/legal/documents";
import { LegalHelp } from "./LegalHelp";
import { CustomerCenterHeader } from "./WebContentShell";

/** Public legal text is rendered on the server, including when JavaScript is disabled. */
export function PublishedLegalDocument({
  document,
  archived = false,
}: {
  document: LegalDocument;
  archived?: boolean;
}) {
  const [year, month, day] = document.effectiveDate.split("-").map(Number);
  return (
    <div className="stitch-surface bg-bg text-text flex h-dvh min-h-0 flex-col overflow-hidden [&>header]:shrink-0">
      <CustomerCenterHeader current={document.path} />

      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto flex min-h-0 w-full max-w-[1200px] flex-1 flex-col gap-4 px-4 pt-4 pb-2 sm:px-8 sm:pt-6 sm:pb-4"
      >
        <div className="flex shrink-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h1 className="m-0 text-[24px] leading-[1.35] font-extrabold sm:text-[32px]">
            {document.title}
          </h1>
          <p className="text-text-sub m-0 text-[14px]">
            시행일{" "}
            <time dateTime={document.effectiveDate}>
              {year}년 {month}월 {day}일
            </time>{" "}
            · 버전 {document.version}
          </p>
        </div>

        <div className="grid min-h-0 min-w-0 flex-1 grid-rows-[auto_minmax(0,1fr)] gap-2 lg:grid-cols-[240px_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)] lg:gap-4">
          <nav
            aria-label="문서 목차"
            className="rounded-card bg-surface flex min-h-0 min-w-0 items-center gap-2 px-3 lg:flex-col lg:items-stretch lg:p-4"
          >
            <h2 className="m-0 shrink-0 text-[14px] font-bold">목차</h2>
            <ol className="m-0 flex min-h-0 min-w-0 list-none gap-1 overflow-auto overscroll-contain p-0 lg:flex-col">
              {document.sections.map((section) => (
                <li key={section.id} className="shrink-0">
                  <a
                    href={`#${section.id}`}
                    className="text-text-sub hover:text-brand-strong flex min-h-10 items-center rounded-sm px-2 py-1 text-[13px] whitespace-nowrap no-underline hover:underline lg:whitespace-normal"
                  >
                    {section.title}
                  </a>
                </li>
              ))}
            </ol>
          </nav>

          <div
            role="region"
            aria-label="문서 본문"
            tabIndex={0}
            className="flex min-h-0 min-w-0 flex-col gap-4 overflow-y-auto overscroll-contain p-0.5 focus-visible:outline-offset-[-3px]"
          >
            <article
              aria-label={document.title}
              className="rounded-card bg-surface flex min-w-0 flex-col gap-[36px] px-[20px] py-[28px] sm:px-[32px] sm:py-[36px]"
            >
              {document.sections.map((section) => (
                <section
                  key={section.id}
                  id={section.id}
                  className="flex min-w-0 scroll-mt-[24px] flex-col gap-[14px]"
                >
                  <h2 className="m-0 text-[19px] leading-[1.6] font-bold sm:text-[21px]">
                    {section.title}
                  </h2>
                  {section.paragraphs?.map((paragraph) => (
                    <p
                      key={paragraph}
                      className="m-0 text-[15px] leading-[1.95] [overflow-wrap:anywhere]"
                    >
                      {paragraph}
                    </p>
                  ))}
                  {section.items && (
                    <ul className="m-0 flex list-disc flex-col gap-[10px] pl-[20px] text-[15px] leading-[1.95]">
                      {section.items.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  )}
                  {section.table && (
                    <div
                      className="border-line overflow-x-auto rounded-sm border border-solid"
                      role="region"
                      aria-label={`${section.title} 표`}
                      tabIndex={0}
                    >
                      <table className="w-full min-w-[580px] border-collapse text-[14px] leading-[1.85]">
                        <thead className="bg-bg">
                          <tr>
                            {section.table.headers.map((header) => (
                              <th
                                key={header}
                                scope="col"
                                className="border-line border-b border-solid px-[16px] py-[12px] text-left align-top font-bold"
                              >
                                {header}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {section.table.rows.map((row) => (
                            <tr key={row[0]}>
                              {row.map((cell, index) =>
                                index === 0 ? (
                                  <th
                                    key={index}
                                    scope="row"
                                    className="border-line-soft min-w-[120px] border-b border-solid px-[16px] py-[14px] text-left align-top font-semibold"
                                  >
                                    {cell}
                                  </th>
                                ) : (
                                  <td
                                    key={index}
                                    className="border-line-soft border-b border-solid px-[16px] py-[14px] align-top [overflow-wrap:anywhere]"
                                  >
                                    {cell}
                                  </td>
                                ),
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {section.links && (
                    <ul className="m-0 flex list-none flex-col gap-[8px] p-0 text-[14px] leading-[1.8]">
                      {section.links.map((link) => (
                        <li key={link.href}>
                          <a
                            href={link.href}
                            className="text-brand-strong [overflow-wrap:anywhere] underline underline-offset-4"
                          >
                            {link.label}
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ))}
            </article>
            <div className="min-w-0">
              <aside
                aria-label="주요 내용"
                className="rounded-card border-line bg-surface mb-4 border border-solid px-[20px] py-[22px] sm:px-[28px]"
              >
                <ul className="m-0 flex list-disc flex-col gap-[8px] pl-[20px] text-[15px] leading-[1.8]">
                  {document.summary.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </aside>

              {!archived && <LegalHelp privacy={document.path === "/privacy"} />}
              <p className="text-text-sub m-0 max-w-[780px] text-[15px] leading-[1.8]">
                {document.description}
              </p>
              <div className="border-line bg-surface mb-[24px] rounded-sm border border-solid p-[16px] text-[14px] leading-[1.8]">
                {archived
                  ? "버전별로 보존한 전문입니다. 현재 적용 문서는 각 문서의 기본 주소에서 확인할 수 있습니다."
                  : "현재 적용 중인 문서입니다. 공고일·시행일과 버전별 전문은 이력에서 확인할 수 있습니다."}{" "}
                <Link href="/legal" className="text-brand-strong underline underline-offset-4">
                  약관·정책 이력 보기
                </Link>
                {archived && (
                  <>
                    {" "}
                    ·{" "}
                    <Link
                      href={document.path}
                      className="text-brand-strong underline underline-offset-4"
                    >
                      현재 적용 문서 보기
                    </Link>
                  </>
                )}
              </div>
            </div>
            <footer className="border-line bg-surface rounded-card border px-4 py-4 text-[13px] leading-[1.8]">
              <div className="text-text-sub mx-auto flex max-w-[1056px] flex-wrap items-center justify-between gap-[12px]">
                <span>
                  무주택자들 ·{" "}
                  <a
                    href={`mailto:${LEGAL_CONTACT}`}
                    className="text-text-sub underline underline-offset-4"
                  >
                    {LEGAL_CONTACT}
                  </a>
                </span>
                <Link href="/" className="text-text-sub underline underline-offset-4">
                  홈으로 돌아가기
                </Link>
              </div>
            </footer>
          </div>
        </div>
      </main>
    </div>
  );
}
