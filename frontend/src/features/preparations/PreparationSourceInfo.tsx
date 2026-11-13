import Link from "next/link";
import { ExternalLink, FileText, Landmark, CircleHelp } from "lucide-react";
import type { Preparation } from "./api";
import { formatWon } from "@/shared/lib/money";
import { routes } from "@/shared/lib/routes";
import { preparationButton } from "./PreparationList";

const channelLabels: Record<string, string> = {
  ONLINE: "온라인",
  ONSITE: "방문",
  EMAIL: "이메일",
  MAIL: "우편",
  FAX: "팩스",
};

export function PreparationSourceInfo({ p }: { p: Preparation }) {
  const guidance = p.source.guidance ?? [];
  const methods = guidance.filter((g) => g.kind === "APPLICATION_METHOD");
  const contacts = guidance.filter((g) => g.kind === "CONTACT");
  const cautions = guidance.filter((g) => g.kind !== "APPLICATION_METHOD" && g.kind !== "CONTACT");
  const schedules = [...(p.source.schedules ?? []), ...(p.source.followUps ?? []).flatMap((f) => f.schedules)];
  const channels = [...new Set(schedules.flatMap((s) => s.channels ?? []))];
  const urls = [
    ...new Set(
      [...methods.map((g) => g.url), ...schedules.map((s) => s.applicationUrl)].filter((u): u is string => Boolean(u)),
    ),
  ];

  return (
    <>
      <section id="application-method" aria-label="신청 방법과 문의처" className="scroll-mt-[90px]">
        <h2 className="flex items-center gap-[8px] text-[21px] font-extrabold">
          <Landmark size={22} className="text-brand" aria-hidden />
          신청 방법과 문의처
        </h2>
        {channels.length > 0 && (
          <p className="text-[15px]">
            접수 방법: <strong>{channels.map((c) => channelLabels[c] ?? c).join(" · ")}</strong>
          </p>
        )}
        {methods.map((g) => (
          <div key={g.id} className="bg-bg rounded-tile mb-[10px] p-[16px]">
            <strong>{g.title ?? "신청 안내"}</strong>
            {g.description && <p className="mb-0 text-[15px] leading-[1.7]">{g.description}</p>}
          </div>
        ))}
        {urls.map((url, i) => (
          <a
            key={url}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="bg-brand-soft text-brand-strong mr-[8px] mb-[10px] inline-flex min-h-[46px] items-center gap-[7px] rounded-sm px-[14px] text-[14px] font-bold no-underline"
          >
            {urls.length === 1 ? "공고에 나온 신청 페이지" : `신청 페이지 ${i + 1}`}
            <ExternalLink size={15} aria-hidden />
          </a>
        ))}
        {schedules.flatMap((s) =>
          (s.places ?? []).map((place, i) => (
            <p key={`${s.id}:place:${i}`} className="text-[14px]">
              방문 접수: {[place.name, place.address, place.detail].filter(Boolean).join(" · ")}
            </p>
          )),
        )}
        {schedules
          .filter((s) => s.applicationEmail)
          .map((s) => (
            <div key={s.id} className="bg-bg rounded-tile my-[10px] p-[14px] text-[14px]">
              <strong>이메일 접수</strong>
              <p>
                <a href={`mailto:${s.applicationEmail!.address}`}>{s.applicationEmail!.address}</a>
              </p>
              {s.applicationEmail?.subjectFormat && <p>메일 제목: {s.applicationEmail.subjectFormat}</p>}
            </div>
          ))}
        {contacts.map((g) => (
          <div key={g.id} className="border-line-soft border-t border-solid py-[12px]">
            <strong className="text-[15px]">{g.title ?? "공고 문의처"}</strong>
            {g.description && <p className="text-[14px]">{g.description}</p>}
            {g.phone && (
              <a href={`tel:${g.phone}`} className="mr-[12px]">
                {g.phone}
              </a>
            )}
            {g.url && (
              <a href={g.url} target="_blank" rel="noopener noreferrer">
                문의 안내 열기
              </a>
            )}
          </div>
        ))}
        {contacts.length === 0 && (
          <p className="text-text-sub text-[13px]">
            문의처 정보가 제공되지 않았어요. 기관 공고 페이지에서 확인해 주세요.
          </p>
        )}
        {methods.length === 0 && channels.length === 0 && urls.length === 0 && (
          <p className="text-text-sub text-[14px]">확인된 신청 방법이 없어요. 기관 원문의 접수 안내를 확인해 주세요.</p>
        )}
      </section>
      <section id="notice-conditions" aria-label="신청 전 확인할 조건" className="scroll-mt-[90px]">
        <h2 className="flex items-center gap-[8px] text-[21px] font-extrabold">
          <CircleHelp size={22} className="text-brand" aria-hidden />
          신청 전 확인할 조건
        </h2>
        <p className="text-text-sub text-[14px]">
          공고에 나온 조건을 정리했어요. 내 조건에 맞는지는 공고 상세에서 확인하세요.
        </p>
        {(p.source.conditions ?? []).length === 0 ? (
          <p className="text-text-sub text-[14px]">아직 정리된 조건이 없어요. 원문에서 신청 자격을 확인해 주세요.</p>
        ) : (
          <ul className="m-0 list-none p-0">
            {p.source.conditions!.map((c, index) => (
              <li key={c.id} className="border-line-soft flex items-start gap-[10px] border-b border-solid py-[13px]">
                <span
                  className="bg-brand-soft text-brand-strong mt-[2px] flex size-[22px] flex-none items-center justify-center rounded-full text-[12px]"
                  aria-hidden
                >
                  {index + 1}
                </span>
                <span className="flex flex-col gap-[5px]">
                  <span className="text-[15px] leading-[1.7]">{c.description || c.originalText}</span>
                  {c.target && <span className="text-text-sub text-[13px]">대상: {c.target}</span>}
                  {c.inReview && (
                    <span className="text-check-text text-[13px] font-bold">공고 원문과 다시 확인 중인 조건이에요</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        {(p.source.selectionRules ?? []).length > 0 && (
          <details className="bg-bg rounded-tile my-[14px] px-[16px] py-[13px]">
            <summary className="min-h-[28px] cursor-pointer text-[14px] font-bold">선정 순위·배점도 확인하기</summary>
            <ul className="mb-0 pl-[20px] text-[14px] leading-[1.8]">
              {p.source.selectionRules!.map((r) => (
                <li key={r.id}>{r.description || r.originalText}</li>
              ))}
            </ul>
          </details>
        )}
        <Link href={routes.notice(p.noticeId)} className={preparationButton}>
          공고 상세에서 내 자격 확인
        </Link>
      </section>
      <section id="notice-money" aria-label="공고에 나온 주거 비용" className="scroll-mt-[90px]">
        <h2 className="text-[21px] font-extrabold">공고에 나온 주거 비용</h2>
        {(p.source.unitTypes ?? []).length > 0 ? (
          <div className="flex flex-col gap-[12px]">
            {p.source.unitTypes!.map((u, i) => (
              <div key={`${u.houseType}:${i}`} className="border-line rounded-tile border border-solid p-[16px]">
                <strong className="text-[16px]">
                  {[u.siteName, u.houseType, u.exclusiveM2 != null ? `${u.exclusiveM2}㎡` : null]
                    .filter(Boolean)
                    .join(" · ") || "모집 주택"}
                </strong>
                {u.targetGroups.length > 0 && (
                  <p className="text-text-sub text-[13px]">가격 적용 대상: {u.targetGroups.join(" · ")}</p>
                )}
                <dl className="mb-0 grid grid-cols-2 gap-[14px]">
                  {[
                    { label: "보증금", value: u.depositWon },
                    { label: "월 임대료", value: u.rentWon },
                  ].map((row) => (
                    <div key={row.label}>
                      <dt className="text-text-sub text-[13px]">{row.label}</dt>
                      <dd className="m-0 mt-[4px] text-[19px] font-extrabold">
                        {row.value != null ? formatWon(row.value) : "원문 확인"}
                      </dd>
                    </div>
                  ))}
                </dl>
                {u.salePriceMinWon != null && (
                  <p className="text-[14px]">
                    분양가: {formatWon(u.salePriceMinWon)}
                    {u.salePriceMaxWon != null &&
                      u.salePriceMaxWon !== u.salePriceMinWon &&
                      ` ~ ${formatWon(u.salePriceMaxWon)}`}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-text-sub text-[14px]">
            현재 확인된 금액이 없어요. 원문에서 납부 금액과 시점을 확인해 주세요.
          </p>
        )}
        <p className="text-text-sub text-[13px] leading-[1.7]">
          가격 적용 대상과 관리비·계약금·납부 시점은 원문에서 함께 확인하세요.
        </p>
        <Link href={routes.loans} className={preparationButton}>
          대출 자격 확인하기
        </Link>
      </section>
      {cautions.length > 0 && (
        <section aria-label="공고의 준비 유의사항">
          <h2 className="text-[21px] font-extrabold">준비할 때 유의할 점</h2>
          {cautions.map((g) => (
            <div key={g.id} className="bg-bg rounded-tile mb-[10px] p-[16px]">
              <strong>{g.title ?? "공고 안내"}</strong>
              {g.description && <p className="mb-0 text-[14px] leading-[1.8]">{g.description}</p>}
            </div>
          ))}
        </section>
      )}
      <section aria-label="공고 원문과 첨부">
        <h2 className="flex items-center gap-[8px] text-[21px] font-extrabold">
          <FileText size={22} className="text-brand" aria-hidden />
          공고 원문과 첨부
        </h2>
        <div className="flex flex-col gap-[8px]">
          {(p.source.files ?? [])
            .filter((f) => f.viewUrl || f.url)
            .map((f) => (
              <a
                key={f.id}
                href={f.viewUrl ?? f.url!}
                target="_blank"
                rel="noopener noreferrer"
                className="border-line text-text flex min-h-[48px] items-center justify-between gap-[10px] rounded-sm border border-solid px-[14px] py-[10px] text-[14px] no-underline"
              >
                <span className="break-all">{f.name}</span>
                <ExternalLink className="text-text-sub flex-none" size={16} aria-hidden />
              </a>
            ))}
        </div>
      </section>
    </>
  );
}
