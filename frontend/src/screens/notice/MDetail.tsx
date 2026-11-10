"use client";

import { MNoticeChatButton, NoticeChat } from "@/components/chat/NoticeChat";
import { ReportButton } from "@/components/report/ReportButton";
import { MFavoriteHeart } from "@/components/favorites/FavoriteButtons";
import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, MapPin } from "lucide-react";
import { MBackHeader, MBottomActions } from "@/components/layout/MBackHeader";
import { MPage } from "@/components/layout/Responsive";
import { EligibilityCard } from "@/components/notice/EligibilityCard";
import { LifeCard } from "@/components/notice/LifeCard";
import { NoticeSections, NoticeToc } from "@/components/notice/NoticeSections";
import { NoticeTags } from "@/components/notice/NoticeTags";
import { PdfViewer } from "@/components/notice/PdfViewer";
import { MRankCard } from "@/components/notice/RankCard";
import { VerdictBadge } from "@/components/ui/Badge";
import { dueText, formatPeriod, statusLabel, pdfSections } from "@/features/notice/format";
import { useNoticeJudgment, withMine, type NoticeJudgment } from "@/features/notice/judgment";
import {
  bySite,
  directionsUrl,
  scrollToVisible,
  toUnit,
  useNoticeUnits,
} from "@/features/notice/units";
import { SitesMap } from "@/components/notice/SitesMap";
import { unitStatus, useUnitPicker } from "@/features/notice/useUnitPicker";
import { UnitPrices } from "@/components/notice/UnitPrices";
import type { StandardNotice } from "@/mocks/notice";
import { noticeParams, useJudgmentViewed } from "@/features/notice/analytics";
import { useNotice } from "@/features/notice/queries";
import { usePdfViewer } from "@/features/notice/usePdfViewer";
import { track } from "@/lib/analytics";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

const MOBILE_BENEFIT_COUNT = 2;

const card = "rounded-card bg-surface mx-[16px] flex flex-col";

/** 처음에 보여주는 집 수 */
const MOBILE_UNIT_COUNT = 5;

/** 실제 API 주택목록: 집을 고르면 가격 · 준비할 돈 · 생활권 · 길찾기 (웹 ApiBlockUnits와 같은 기능) */
function MApiUnits({
  notice,
  judgment,
  onShowLife,
}: {
  notice: StandardNotice;
  judgment: NoticeJudgment | null;
  onShowLife: (siteId: string) => void;
}) {
  const q = useNoticeUnits(notice.id, true);
  const [all, setAll] = useState(false);
  const sites = useMemo(() => notice.sites ?? [], [notice.sites]);
  const units = useMemo(
    () => (q.data?.pages ?? []).flatMap((p) => p.items.map((u) => toUnit(u, sites, judgment))),
    [q.data, sites, judgment],
  );
  const {
    onlyOk,
    setOnlyOk,
    shown: filtered,
    selected,
    select,
    countAll,
    countOk,
  } = useUnitPicker(units);
  if (q.isPending || units.length === 0) return null;
  const shown = all ? filtered : filtered.slice(0, MOBILE_UNIT_COUNT);
  const located = sites.some((s) => s.lat !== null && s.lng !== null);
  const site = sites.find((s) => s.id === selected?.siteId);
  const directions = directionsUrl(site);
  // 필터를 바꾸면 처음 몇 집부터 다시 보여요
  const filter = (ok: boolean) => {
    setOnlyOk(ok);
    setAll(false);
  };
  const chip = (on: boolean) =>
    cn(
      "rounded-pill min-h-[36px] cursor-pointer border-0 px-[12px] text-[13px] font-bold",
      on ? "bg-text text-white" : "bg-fill text-text-sub",
    );

  return (
    <section aria-labelledby="units-h" className={cn(card, "gap-[10px] px-[20px] py-[16px]")}>
      <div className="flex flex-col gap-[2px]">
        <h3 id="units-h" className="m-0 text-[17px] font-extrabold">
          공급 주택 목록 <span className="text-brand">{countAll}곳</span>
        </h3>
        <span className="text-text-sub text-[13px]">
          집을 고르면 가격과 준비할 돈{located ? ", 지도 위치" : ""}를 보여드려요
        </span>
      </div>
      <div role="group" aria-label="목록 필터" className="flex gap-[6px]">
        <button
          type="button"
          aria-pressed={!onlyOk}
          onClick={() => filter(false)}
          className={chip(!onlyOk)}
        >
          전체 {countAll}
        </button>
        <button
          type="button"
          aria-pressed={onlyOk}
          onClick={() => filter(true)}
          className={chip(onlyOk)}
        >
          신청 가능만 {countOk}
        </button>
      </div>
      {located && (
        <SitesMap
          sites={sites}
          selectedSiteId={selected?.siteId}
          onSelectSite={(siteId) => {
            const first = units.find((u) => u.siteId === siteId);
            if (first) select(first.id);
          }}
          className="rounded-tile h-[220px] w-full overflow-hidden"
        />
      )}
      {bySite(shown, filtered).map((g) => (
        <div key={g.key} className="flex flex-col gap-[8px]">
          {g.name && (
            <h4 className="text-text-sub m-0 text-[14px] font-extrabold">
              {g.name} <span className="text-brand">{g.count}호</span>
              {g.lifeScore !== undefined && (
                <span className="text-text-tertiary font-bold"> · 생활권 {g.lifeScore}점</span>
              )}
            </h4>
          )}
          <ul aria-label={g.name} className="m-0 flex list-none flex-col gap-[8px] p-0">
            {g.units.map((u) => {
              const on = selected?.id === u.id;
              return (
                <li key={u.id}>
                  <button
                    type="button"
                    aria-pressed={on}
                    onClick={() => select(u.id)}
                    className={cn(
                      "rounded-tile text-text flex w-full cursor-pointer flex-col gap-[3px] border-2 border-solid px-[14px] py-[12px] text-left",
                      on ? "border-brand bg-brand-soft" : "bg-bg border-transparent",
                    )}
                  >
                    <span className="flex items-center justify-between gap-[8px]">
                      <span className="text-[15px] font-bold">
                        {g.name ? (u.label ?? u.name) : u.name}
                      </span>
                      <span
                        className={cn(
                          "rounded-badge flex-none px-[8px] py-[3px] text-[12px] font-bold",
                          u.ok ? "bg-ok-bg text-ok-text" : "bg-surface text-text-sub",
                        )}
                      >
                        {unitStatus(u)}
                      </span>
                    </span>
                    <span className="text-text-sub text-[13px]">
                      {u.type} · {u.area} · {u.floor}
                    </span>
                    <UnitPrices unit={u} />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      {(filtered.length > shown.length || q.hasNextPage) && (
        <button
          type="button"
          onClick={() => (filtered.length > shown.length ? setAll(true) : void q.fetchNextPage())}
          disabled={q.isFetchingNextPage}
          className="bg-fill text-text min-h-[44px] cursor-pointer rounded-sm border-0 text-[14px] font-bold disabled:opacity-60"
        >
          {q.isFetchingNextPage ? "불러오는 중" : "더 보기"}
        </button>
      )}
      {selected && (
        <div
          aria-live="polite"
          className="bg-bg flex flex-col gap-[6px] rounded-[18px] px-[16px] py-[14px]"
        >
          <span className="flex flex-wrap items-center gap-[6px]">
            <span className="text-[16px] font-extrabold">{selected.name}</span>
            <span
              className={cn(
                "rounded-badge px-[8px] py-[3px] text-[12px] font-bold",
                selected.ok ? "bg-ok-bg text-ok-text" : "bg-surface text-text-sub",
              )}
            >
              {unitStatus(selected)}
            </span>
          </span>
          <span className="text-text-sub text-[13px]">
            {[`${selected.type} ${selected.area}`, selected.floor, selected.station]
              .filter(Boolean)
              .join(" · ")}
          </span>
          {selected.prices ? (
            selected.prices.map((p) => (
              <span key={p.target} className="text-[14px]">
                <span className="text-text-sub mr-[6px] text-[13px]">{p.target}</span>
                보증금 <strong>{p.deposit}</strong> · <strong>{p.rent}</strong>
              </span>
            ))
          ) : (
            <span className="text-[14px]">
              보증금 <strong>{selected.deposit}</strong> · <strong>{selected.rent}</strong>
            </span>
          )}
          <span className="text-[14px]">
            준비할 돈 <strong className="text-brand-strong">{selected.prep}</strong>
          </span>
          {((selected.siteId && selected.lifeScore !== undefined) || directions) && (
            <div className="grid grid-cols-2 gap-[8px] pt-[4px]">
              {selected.siteId && selected.lifeScore !== undefined && (
                <button
                  type="button"
                  onClick={() => onShowLife(selected.siteId!)}
                  className="bg-surface text-text inline-flex min-h-[44px] cursor-pointer items-center justify-center gap-[6px] rounded-sm border-0 text-[14px] font-bold"
                >
                  <MapPin size={16} aria-hidden />
                  생활권 {selected.lifeScore}점
                </button>
              )}
              {directions && (
                <a
                  href={directions}
                  target="_blank"
                  rel="noreferrer"
                  className="bg-brand inline-flex min-h-[44px] items-center justify-center gap-[6px] rounded-sm text-[14px] font-bold text-white no-underline hover:text-white"
                >
                  <ArrowRight size={16} strokeWidth={2.2} aria-hidden />
                  길찾기
                </a>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export function MDetail({ id }: { id: string }) {
  const { data, loading, error } = useNotice(id);
  const n = data?.kind === "standard" ? data : undefined;
  const j = useNoticeJudgment(n);
  const pdf = usePdfViewer();
  const [lifeSite, setLifeSite] = useState<string>();
  const [allBenefits, setAllBenefits] = useState(false);
  useJudgmentViewed(id, n);
  if (!n) {
    return (
      <MPage>
        <MBackHeader title="공고 상세" backHref={routes.homes} />
        {(loading || error) && (
          <p
            role={error ? "alert" : undefined}
            className="text-text-sub m-0 px-[20px] py-[64px] text-center text-[15px]"
          >
            {error
              ? "공고를 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요"
              : "공고를 불러오는 중이에요"}
          </p>
        )}
      </MPage>
    );
  }
  const benefitsAll = n.benefits ?? [];
  const benefits = allBenefits ? benefitsAll : benefitsAll.slice(0, MOBILE_BENEFIT_COUNT);
  /** 주택목록에서 고른 집 단지의 생활권으로 (웹과 같아요) */
  const showLife = (siteId: string) => {
    setLifeSite(siteId);
    scrollToVisible("life");
  };
  const doc = withMine(n.doc, j.judgment?.mineTypes ?? []);
  const money = j.judgment?.money;
  const pdfUrl = doc.source.pdfUrl;
  /** 원문 PDF가 있으면 시트로 열고, 없으면 기관 사이트로 */
  const openOriginal = (page = 1, label?: string) => {
    track("notice_source_open", { ...noticeParams(n), via: pdfUrl ? "pdf" : "site" });
    if (pdfUrl) pdf.show(page, label);
    else window.open(doc.source.detailUrl, "_blank", "noreferrer");
  };

  return (
    <MPage>
      <MBackHeader title="공고 상세" backHref={routes.homes} />
      <main className="flex flex-1 flex-col gap-[12px] pb-[24px]">
        <section className="bg-surface flex flex-col gap-[12px] px-[20px] pt-[20px] pb-[22px]">
          <NoticeTags
            verdict={j.judgment?.verdict ?? "check"}
            rank={n.ranking?.myRank}
            due={dueText(n)}
            tags={n.tags}
            size="md"
          />
          <h2 className="tracking-h1 m-0 text-[24px] font-extrabold">{n.title}</h2>
          <span className="text-text-sub text-[14px] leading-[1.5]">{n.meta}</span>
          {doc.summary && <p className="m-0 text-[15px] leading-[1.6]">{doc.summary}</p>}
          <dl className="m-0 grid grid-cols-2 gap-[8px]">
            {n.facts.map((f) => (
              <div key={f.label} className="bg-bg rounded-control px-[14px] py-[12px]">
                <dt className="text-text-sub text-[12px]">{f.label}</dt>
                <dd className="mx-0 mt-[3px] mb-0 text-[15px] font-extrabold">{f.value}</dd>
              </div>
            ))}
          </dl>
          {doc.applyPeriod && (
            <div className="bg-brand-soft rounded-control flex flex-col gap-[2px] px-[14px] py-[12px]">
              <span className="text-brand-strong text-[12px] font-bold">
                신청 기간 · {statusLabel[doc.status]}
              </span>
              <span className="text-[15px] font-extrabold">
                {formatPeriod(doc.applyPeriod.start, doc.applyPeriod.end)}
              </span>
              {doc.applyPeriod.note && (
                <span className="text-text-sub text-[13px]">{doc.applyPeriod.note}</span>
              )}
            </div>
          )}
        </section>

        {money && (
          <section
            aria-labelledby="money-h"
            className="rounded-card bg-brand-deep mx-[16px] flex flex-col gap-[10px] p-[20px] text-white"
          >
            <h3 id="money-h" className="text-brand-deep-text m-0 text-[15px] font-bold">
              내가 준비할 돈 · {money.type}
            </h3>
            <span className="flex justify-between text-[15px]">
              <span>임대보증금</span>
              <span>{money.deposit}</span>
            </span>
            {money.loan && (
              <span className="flex justify-between text-[15px]">
                <span>{money.loanName}</span>
                <span>− {money.loan}</span>
              </span>
            )}
            <span className="flex items-baseline justify-between border-t border-solid border-white/14 pt-[10px]">
              <span className="text-[15px] font-bold">준비할 돈</span>
              <span className="tracking-title text-[28px] font-extrabold">{money.prep}</span>
            </span>
            {money.note && <span className="text-brand-deep-text text-[13px]">{money.note}</span>}
          </section>
        )}

        <EligibilityCard
          judgment={j.judgment}
          loading={j.loading}
          error={j.error}
          variant="mobile"
          onOpenOriginal={(page) => openOriginal(page ?? doc.pages.eligibility ?? 1, "신청 자격")}
        />

        {n.hasUnits && <MApiUnits notice={n} judgment={j.judgment} onShowLife={showLife} />}

        {n.life && (
          <LifeCard life={n.life} variant="mobile" siteId={lifeSite} onSiteChange={setLifeSite} />
        )}

        {n.ranking && <MRankCard ranking={n.ranking} />}

        <NoticeToc doc={doc} variant="mobile" />
        <NoticeSections doc={doc} variant="mobile" onOpenPage={pdfUrl ? openOriginal : undefined} />

        <NoticeChat noticeId={n.id} variant="mobile" />

        {benefits.length > 0 && (
          <section aria-labelledby="bn-h" className={cn(card, "px-[20px] pt-[16px] pb-[6px]")}>
            <h3 id="bn-h" className="mx-0 mt-0 mb-[2px] text-[17px] font-extrabold">
              입주하면 받을 수 있는 혜택
            </h3>
            {n.benefitArea && (
              <span className="text-text-tertiary mb-[4px] text-[13px]">
                {n.benefitArea} · 내 조건 판정
              </span>
            )}
            {benefits.map((b, i) => (
              <Link
                key={b.id}
                href={routes.benefit(b.id)}
                className={cn(
                  "text-text hover:text-text flex items-center justify-between gap-[10px] py-[12px] no-underline",
                  i < benefits.length - 1 && "border-line-soft border-b border-solid",
                )}
              >
                <span className="flex flex-col gap-[2px]">
                  <span className="text-[15px] font-bold">{b.title}</span>
                  <span className="text-text-sub text-[13px]">{b.desc}</span>
                </span>
                <VerdictBadge verdict={b.verdict} size="xs" className="flex-none" />
              </Link>
            ))}
            {benefitsAll.length > benefits.length && (
              <button
                type="button"
                onClick={() => setAllBenefits(true)}
                className="text-text-sub min-h-[44px] cursor-pointer border-0 bg-transparent text-[14px] font-bold"
              >
                {benefitsAll.length - benefits.length}개 더 보기
              </button>
            )}
          </section>
        )}

        <span className="text-text-sub px-[16px] pt-[4px] text-center text-[13px]">
          판정은 참고용이에요. 신청 전에 원문을 확인해 주세요
        </span>
        <ReportButton
          target={{ kind: "notice", id: n.id }}
          screen="공고 상세 (모바일)"
          className="px-[16px]"
        />
      </main>
      <MBottomActions>
        <MFavoriteHeart
          type="NOTICE"
          id={n.id}
          onAdd={() => track("notice_bookmark", noticeParams(n))}
        />
        <MNoticeChatButton noticeId={n.id} />
        <button
          type="button"
          onClick={() => openOriginal()}
          className="rounded-control bg-brand flex min-h-[56px] flex-1 cursor-pointer items-center justify-center border-0 text-[17px] font-extrabold text-white"
        >
          {n.agency} 공고 원문 보기
        </button>
      </MBottomActions>
      {pdfUrl && (
        <PdfViewer
          open={pdf.open}
          onClose={pdf.close}
          src={pdfUrl}
          fileName={doc.source.fileName}
          detailUrl={doc.source.detailUrl}
          target={pdf.target}
          sections={pdfSections(doc)}
          onJump={pdf.show}
          variant="mobile"
        />
      )}
    </MPage>
  );
}
