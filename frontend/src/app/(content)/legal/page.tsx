import type { Metadata } from "next";
import Link from "next/link";
import { LEGAL_ORIGIN } from "@/features/content/legal/documents";
import { legalVersions, legalVersionPath } from "@/features/content/legal/history";
import { legalAnnouncements } from "@/features/content/legal/announcements";

export const metadata: Metadata = {
  title: "약관·정책 이력 | 무주택자들",
  alternates: { canonical: `${LEGAL_ORIGIN}/legal` },
};

export default function LegalHistoryPage() {
  return (
    <main className="text-text mx-auto w-full max-w-[960px] px-[20px] py-[40px] sm:px-[32px]">
      <Link href="/" className="text-brand-strong font-bold underline underline-offset-4">
        무주택자들 홈
      </Link>
      <h1 className="mt-[28px] mb-[12px] text-[30px] font-extrabold">약관·정책 이력</h1>
      <p className="text-text-sub mb-[28px] text-[15px] leading-[1.9]">
        현재 적용 문서와 공개한 버전의 전문을 확인할 수 있습니다. 공고일은 문서를 알린 날이며,
        시행일은 그 내용이 적용되는 날입니다.
      </p>
      <section aria-label="공개한 문서 버전" className="mb-[32px] grid gap-[16px] sm:grid-cols-2">
        {legalVersions.map(({ kind, publishedDate, reason, document }) => (
          <article
            key={`${kind}-${document.version}`}
            className="border-line bg-surface rounded-card border border-solid p-[24px] text-[14px] leading-[1.9]"
          >
            <h2 className="m-0 mb-[12px] text-[20px] font-bold">
              {document.title} v{document.version}
            </h2>
            <dl className="m-0 grid grid-cols-[64px_1fr] gap-x-[12px] gap-y-[6px]">
              <dt>공고일</dt>
              <dd className="m-0">
                <time dateTime={publishedDate}>{publishedDate}</time>
              </dd>
              <dt>시행일</dt>
              <dd className="m-0">
                <time dateTime={document.effectiveDate}>{document.effectiveDate}</time>
              </dd>
              <dt>변경 사유</dt>
              <dd className="m-0">{reason}</dd>
            </dl>
            <div className="mt-[16px] flex flex-wrap gap-[16px]">
              <Link href={document.path} className="text-brand-strong underline underline-offset-4">
                현재 적용 문서
              </Link>
              <Link
                href={legalVersionPath(kind, document.version)}
                className="text-brand-strong underline underline-offset-4"
              >
                v{document.version} 전문 보기
              </Link>
            </div>
          </article>
        ))}
      </section>
      <section
        aria-label="변경 안내"
        className="border-line bg-surface rounded-card border border-solid p-[24px] text-[15px] leading-[1.9]"
      >
        <h2 className="m-0 mb-[16px] text-[21px] font-bold">변경 안내</h2>
        {legalAnnouncements.map((notice) => (
          <div key={notice.id}>
            <p className="text-text-sub m-0 text-[14px]">게시일 {notice.date}</p>
            <h3 className="my-[12px] text-[17px] font-bold">{notice.title}</h3>
            {notice.body.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
        ))}
        <p className="text-text-sub mb-0">
          향후 전문을 개정하면 기존 버전을 보존하고 변경 이유·내용·공고일·시행일을 안내합니다.
          현재는 최초 버전만 있으며, 아직 존재하지 않는 개정안이나 과거 버전은 표시하지 않습니다.
        </p>
        <Link
          href="/announcements"
          className="text-brand-strong mt-[16px] inline-block underline underline-offset-4"
        >
          공지사항 보기
        </Link>
      </section>
    </main>
  );
}
