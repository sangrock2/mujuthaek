import { documentsBySubmission } from "../documents";
import type { NoticeDocumentItem } from "../mocks/notice-doc";

export function DocumentChecklist({ items }: { items: NoticeDocumentItem[] }) {
  return (
    <div className="flex flex-col gap-[16px] px-[16px] pt-[4px] pb-[16px]">
      {documentsBySubmission(items).map(([stage, documents]) => (
        <section key={stage} aria-label={stage} className="flex flex-col gap-[10px]">
          <h4 className="text-text-sub m-0 text-[14px] font-bold">제출 시점 · {stage}</h4>
          <ul className="m-0 flex list-none flex-col gap-[12px] p-0">
            {documents.map((d) => (
              <li key={d.id} className="flex flex-col gap-[2px]">
                <span className="text-[15px] font-bold">{d.name}</span>
                <span className="text-brand-strong text-[13px] font-semibold">
                  제출 대상 ·{" "}
                  {d.appliesTo || (d.submissionTime ? "원문 확인" : d.when) || "원문 확인"}
                </span>
                <span className="text-text-sub text-[13px] leading-[1.5]">{d.desc}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
