"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminTitle, AdminTitleRow } from "@/components/admin/AdminShell";
import { NotificationPanel } from "@/screens/admin/AdminWebNotifications";
import {
  useAdminBotTraffic,
  useAdminRealtime,
  useAdminTraffic,
  useNoticeTitles,
} from "@/features/admin/queries";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type {
  BotAccess,
  BotTrafficData,
  NoticeView,
  ClientKind,
  TrafficData,
  TrafficItem,
} from "@/mocks/admin-traffic";

type Tab = "overview" | "acquisition" | "engagement" | "bots" | "notifications";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "개요" },
  { key: "acquisition", label: "유입" },
  { key: "engagement", label: "이용 흐름" },
  { key: "bots", label: "봇·보안" },
  { key: "notifications", label: "알림" },
];
const PERIODS = [7, 28, 90];

// GA 기본 채널 이름 → 화면 말
const CHANNEL_KO: Record<string, string> = {
  "Organic Search": "검색",
  Direct: "직접 방문",
  "Organic Social": "SNS·메신저 공유",
  Referral: "다른 사이트",
  "Paid Search": "검색 광고",
  "Paid Social": "SNS 광고",
  Display: "배너 광고",
  Email: "메일",
  "Organic Video": "동영상",
  Unassigned: "분류 안 됨",
};
const DEVICE_KO: Record<string, string> = { mobile: "모바일", desktop: "PC", tablet: "태블릿" };
// GA는 지역 이름을 영어로 줘요
const SIDO_KO: Record<string, string> = {
  Seoul: "서울",
  Busan: "부산",
  Daegu: "대구",
  Incheon: "인천",
  Gwangju: "광주",
  Daejeon: "대전",
  Ulsan: "울산",
  Sejong: "세종",
  "Sejong-si": "세종",
  "Gyeonggi-do": "경기",
  "Gangwon-do": "강원",
  "Gangwon State": "강원",
  "Chungcheongbuk-do": "충북",
  "North Chungcheong": "충북",
  "Chungcheongnam-do": "충남",
  "South Chungcheong": "충남",
  "Jeollabuk-do": "전북",
  "Jeonbuk State": "전북",
  "North Jeolla": "전북",
  "Jeollanam-do": "전남",
  "South Jeolla": "전남",
  "Gyeongsangbuk-do": "경북",
  "North Gyeongsang": "경북",
  "Gyeongsangnam-do": "경남",
  "South Gyeongsang": "경남",
  "Jeju-do": "제주",
  Jeju: "제주",
  "(not set)": "알 수 없음",
};
const CLIENT: Record<ClientKind, { label: string; color: string }> = {
  HUMAN: { label: "사람", color: "bg-brand" },
  SEARCH_BOT: { label: "검색엔진 봇", color: "bg-text-sub" },
  PREVIEW_BOT: { label: "링크 미리보기", color: "bg-check-text" },
  TOOL: { label: "도구·자동화", color: "bg-danger-text" },
  MONITOR: { label: "상태 확인", color: "bg-line" },
  UNKNOWN: { label: "알 수 없음", color: "bg-warn-dot" },
};
const STATUS_KO: Record<string, string> = {
  "401": "401 로그인 필요",
  "403": "403 권한 없음",
  "404": "404 없는 주소",
  "429": "429 요청 제한",
  "5xx": "5xx 서버 오류",
};

const num = (n: number) => n.toLocaleString("ko-KR");
const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);
const shortDay = (iso: string) => {
  const [, m, d] = iso.split("-").map(Number);
  return `${m}/${d}`;
};
const when = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("ko-KR", {
        timeZone: "Asia/Seoul",
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "-";

export function AdminWebTraffic() {
  const [tab, setTab] = useState<Tab>("overview");
  const [days, setDays] = useState(7);

  return (
    <>
      <AdminTitleRow>
        <AdminTitle
          title="트래픽"
          desc="방문·유입·이용 흐름은 Google Analytics(통계에 동의한 사람만), 가입·로그인·봇은 서버 기록, 알림은 발송 결과와 받은 회원이 보고 눌렀는지예요"
        />
        <div className="flex flex-wrap gap-[8px]">
          <Segmented
            label="기간"
            options={PERIODS.map((d) => ({ key: String(d), label: `${d}일` }))}
            value={String(days)}
            onChange={(v) => setDays(Number(v))}
          />
          <Segmented
            label="트래픽 탭"
            options={TABS}
            value={tab}
            onChange={(v) => setTab(v as Tab)}
          />
        </div>
      </AdminTitleRow>

      {tab === "notifications" ? (
        <NotificationPanel days={days} />
      ) : tab === "bots" ? (
        <BotsPanel days={Math.min(days, 30)} />
      ) : (
        <GaPanels tab={tab} days={days} />
      )}
    </>
  );
}

function GaPanels({ tab, days }: { tab: Tab; days: number }) {
  const { data, isPending, isError } = useAdminTraffic(days);
  if (isPending) return <Empty text="불러오는 중이에요" />;
  if (isError || !data)
    return <Empty text="트래픽을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요" />;
  return (
    <>
      {!data.ga.connected && (
        <div
          role="status"
          className="rounded-card bg-check-bg text-check-text px-[20px] py-[14px] text-[14px] font-bold"
        >
          {data.ga.error ?? "GA 숫자를 불러오지 못했어요"} · 서버 숫자만 보여요
        </div>
      )}
      {tab === "overview" && <Overview data={data} />}
      {tab === "acquisition" && <Acquisition ga={data.ga} />}
      {tab === "engagement" && <Engagement ga={data.ga} />}
      {data.ga.fetchedAt && (
        <span className="text-text-sub text-[13px]">
          GA에서 가져온 시각 {when(data.ga.fetchedAt)} · GA 숫자는 한 시간마다 새로 받아요
        </span>
      )}
    </>
  );
}

function Overview({ data }: { data: TrafficData }) {
  const ga = data.ga.daily;
  const server = data.server;
  const dates = [...new Set([...ga.map((d) => d.date), ...server.map((d) => d.date)])].sort();
  const gaByDay = new Map(ga.map((d) => [d.date, d]));
  const serverByDay = new Map(server.map((d) => [d.date, d]));
  const today = ga.at(-1);
  const maxUsers = Math.max(1, ...ga.map((d) => d.activeUsers));

  return (
    <>
      <Realtime />
      <section
        aria-label="요약"
        className="grid gap-[14px]"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))" }}
      >
        <Stat
          label="오늘 방문자"
          value={today ? num(today.activeUsers) : "-"}
          note="GA 활성 사용자"
        />
        <Stat
          label={`${data.days}일 신규 사용자`}
          value={num(sum(ga.map((d) => d.newUsers)))}
          note="처음 들어온 사람"
        />
        <Stat
          label={`${data.days}일 페이지뷰`}
          value={num(sum(ga.map((d) => d.pageViews)))}
          note={`세션 ${num(sum(ga.map((d) => d.sessions)))}`}
        />
        <Stat
          label={`${data.days}일 가입`}
          value={num(sum(server.map((d) => d.signups)))}
          note={`로그인 ${num(sum(server.map((d) => d.logins)))} · 실패 ${num(sum(server.map((d) => d.loginFailures)))}`}
        />
      </section>

      <Card
        title="일별 방문자"
        desc="막대는 GA 활성 사용자, 표의 가입·로그인·봇 요청은 서버 기록이에요"
      >
        {ga.length > 0 && (
          <div
            className="flex h-[140px] items-end gap-[4px] pt-[8px]"
            aria-label="일별 방문자 막대"
          >
            {ga.map((d) => (
              <div
                key={d.date}
                className="flex min-w-0 flex-1 flex-col items-center justify-end gap-[4px]"
              >
                <span className="text-text-sub text-[11px]">{num(d.activeUsers)}</span>
                <div
                  className="bg-brand w-full rounded-t-[4px]"
                  style={{ height: `${Math.max(2, (d.activeUsers / maxUsers) * 100)}px` }}
                  title={`${d.date} 방문자 ${num(d.activeUsers)}`}
                />
                <span className="text-text-sub text-[11px]">{shortDay(d.date)}</span>
              </div>
            ))}
          </div>
        )}
        <Table
          head={[
            "날짜",
            "방문자",
            "신규",
            "페이지뷰",
            "가입",
            "로그인",
            "로그인 실패",
            "봇 요청",
            "서버 오류",
          ]}
          rows={[...dates].reverse().map((date) => {
            const g = gaByDay.get(date);
            const s = serverByDay.get(date);
            return [
              date,
              g ? num(g.activeUsers) : "-",
              g ? num(g.newUsers) : "-",
              g ? num(g.pageViews) : "-",
              s ? num(s.signups) : "0",
              s ? num(s.logins) : "0",
              s ? num(s.loginFailures) : "0",
              s ? num(s.botRequests) : "0",
              s ? num(s.serverErrors) : "0",
            ];
          })}
        />
      </Card>
    </>
  );
}

function Acquisition({ ga }: { ga: TrafficData["ga"] }) {
  return (
    <Grid>
      <Card title="유입 경로" desc="세션 기준">
        <BarList items={ga.channels} label={(n) => CHANNEL_KO[n] ?? n} unit="세션" />
      </Card>
      <Card title="들어온 곳" desc="검색 엔진·사이트·앱 이름">
        <BarList
          items={ga.sources}
          label={(n) => (n === "(direct)" ? "직접 방문" : n)}
          unit="세션"
        />
      </Card>
      <Card title="캠페인" desc="공유 링크 등에 붙인 캠페인 이름 (utm_campaign)">
        <BarList
          items={ga.campaigns.filter((c) => c.name !== "(not set)" && c.name !== "(direct)")}
          unit="세션"
        />
      </Card>
      <Card title="처음 들어온 페이지" desc="세션이 시작된 화면">
        <BarList items={ga.landingPages} unit="세션" />
      </Card>
    </Grid>
  );
}

function Engagement({ ga }: { ga: TrafficData["ga"] }) {
  const first = Math.max(1, ga.funnel[0]?.users ?? 1);
  return (
    <>
      <Card title="이용 흐름" desc="각 단계를 한 사람 수(괄호는 횟수). 비율은 방문한 사람 대비예요">
        <ol className="m-0 flex list-none flex-col gap-[10px] p-0">
          {ga.funnel.map((f) => {
            const share = Math.round((f.users / first) * 100);
            return (
              <li key={f.event} className="flex flex-col gap-[4px]">
                <div className="flex items-baseline justify-between gap-[12px] text-[14px]">
                  <span className="font-bold">{f.label}</span>
                  <span className="text-text-sub">
                    {num(f.users)}명 ({num(f.count)}회) · {share}%
                  </span>
                </div>
                <Bar share={share} />
              </li>
            );
          })}
        </ol>
      </Card>
      <Grid>
        <Card
          title="많이 본 공고 TOP 10"
          desc="공고 상세 페이지뷰 · 같은 공고의 하위 화면은 합쳐요"
        >
          <PopularNotices items={ga.popularNotices} />
        </Card>
        <Card title="많이 본 페이지" desc="페이지뷰">
          <BarList items={ga.pages} unit="회" />
        </Card>
        <Card title="기기" desc="활성 사용자">
          <BarList items={ga.devices} label={(n) => DEVICE_KO[n] ?? n} unit="명" />
        </Card>
        <Card title="브라우저" desc="활성 사용자">
          <BarList items={ga.browsers} unit="명" />
        </Card>
        <Card title="지역" desc="활성 사용자(시·도)">
          <BarList items={ga.regions} label={(n) => SIDO_KO[n] ?? n} unit="명" />
        </Card>
      </Grid>
    </>
  );
}

function BotsPanel({ days }: { days: number }) {
  const { data, isPending, isError } = useAdminBotTraffic(days);
  if (isPending) return <Empty text="불러오는 중이에요" />;
  if (isError || !data) return <Empty text="봇·보안 기록을 불러오지 못했어요" />;
  return <Bots data={data} />;
}

function Bots({ data }: { data: BotTrafficData }) {
  const dates = [...new Set(data.clients.map((c) => c.date))].sort();
  const kinds = Object.keys(CLIENT) as ClientKind[];
  const perDay = dates.map((date) => {
    const rows = data.clients.filter((c) => c.date === date);
    return { date, total: sum(rows.map((r) => r.requests)), rows };
  });
  const totals = kinds
    .map((k) => ({ k, n: sum(data.clients.filter((c) => c.client === k).map((c) => c.requests)) }))
    .filter((t) => t.n > 0);
  const all = Math.max(1, sum(totals.map((t) => t.n)));

  return (
    <>
      <span className="text-text-sub text-[13px]">
        서비스 요청과 화면 접속을 함께 세요. 화면 접속은 오류 숫자에는 들어가지 않아요. IP는 마지막
        자리를 가려 보여 주고, 원본은 14일 뒤 지워요
      </span>
      <Card title="보낸 쪽별 요청" desc={`${data.days}일`}>
        <div className="flex flex-wrap gap-[12px] text-[13px]">
          {totals.map((t) => (
            <span key={t.k} className="inline-flex items-center gap-[6px]">
              <span className={cn("size-[10px] rounded-[3px]", CLIENT[t.k].color)} aria-hidden />
              {CLIENT[t.k].label} {num(t.n)} ({Math.round((t.n / all) * 100)}%)
            </span>
          ))}
        </div>
        <div className="flex flex-col gap-[6px]">
          {perDay.map((d) => (
            <div key={d.date} className="flex items-center gap-[10px] text-[13px]">
              <span className="text-text-sub w-[44px] flex-none">{shortDay(d.date)}</span>
              <div className="bg-fill flex h-[14px] min-w-0 flex-1 overflow-hidden rounded-[4px]">
                {kinds.map((k) => {
                  const n = d.rows.find((r) => r.client === k)?.requests ?? 0;
                  return n ? (
                    <div
                      key={k}
                      className={CLIENT[k].color}
                      style={{ width: `${(n / Math.max(1, d.total)) * 100}%` }}
                      title={`${CLIENT[k].label} ${num(n)}`}
                    />
                  ) : null;
                })}
              </div>
              <span className="w-[64px] flex-none text-right">{num(d.total)}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card title="거절·오류 응답" desc="많이 늘면 공격·고장 신호예요">
        <div className="flex flex-wrap gap-[8px]">
          {data.statuses.length === 0 && <span className="text-text-sub text-[14px]">없어요</span>}
          {data.statuses.map((s) => (
            <span
              key={s.group}
              className={cn(
                "rounded-tag px-[10px] py-[6px] text-[13px] font-bold",
                s.group === "5xx" || s.group === "429"
                  ? "bg-danger-bg text-danger-text"
                  : "bg-fill text-text",
              )}
            >
              {STATUS_KO[s.group] ?? s.group} · {num(s.requests)}
            </span>
          ))}
        </div>
      </Card>

      <Card title="요청이 많은 곳" desc="1분 최대가 크면 빠르게 반복하는 자동화일 수 있어요">
        <Table
          head={["IP", "종류", "요청", "1분 최대", "많이 부른 경로", "처음", "마지막"]}
          rows={data.topSources.map((s) => [
            s.maskedIp ?? `해시 ${s.key?.slice(0, 8) ?? "-"}`,
            CLIENT[s.client]?.label ?? s.client,
            num(s.requests),
            num(s.peakPerMinute),
            s.topPath,
            when(s.firstSeen),
            when(s.lastSeen),
          ])}
        />
      </Card>

      <Grid>
        <Card title="봇이 많이 온 경로" desc="사람이 아닌 요청 순">
          <Table
            head={["경로", "봇", "사람"]}
            rows={data.topBotPaths.map((p) => [p.path, num(p.botRequests), num(p.humanRequests)])}
          />
        </Card>
        <Card title="로그인 실패" desc="최근 순">
          <AccessList items={data.loginFailures} />
        </Card>
      </Grid>
      <Card title="관리자 접근 기록" desc="관리자 화면에서 보낸 요청 (누가 했는지는 남기지 않아요)">
        <AccessList items={data.adminAccess} />
      </Card>
    </>
  );
}

// ---------- 작은 부품 ----------

function Segmented({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { key: string; label: string }[];
  value: string;
  onChange: (key: string) => void;
}) {
  return (
    <div role="tablist" aria-label={label} className="rounded-control bg-surface flex p-[4px]">
      {options.map((o) => {
        const on = o.key === value;
        return (
          <button
            key={o.key}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(o.key)}
            className={cn(
              "min-h-[42px] cursor-pointer rounded-[10px] border-0 px-[14px] text-[15px] font-bold",
              on ? "bg-text text-white" : "text-text-sub bg-transparent",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** 지금 접속자 (GA 실시간: 동의한 사람만, 최근 30분) */
function Realtime() {
  const { data } = useAdminRealtime();
  if (!data) return null;
  if (!data.connected) {
    return (
      <div className="rounded-card bg-surface text-text-sub px-[24px] py-[16px] text-[14px]">
        지금 접속자 · {data.error ?? "GA 실시간 숫자를 불러오지 못했어요"}
      </div>
    );
  }
  return (
    <section
      aria-label="지금 접속자"
      className="rounded-card bg-surface flex flex-wrap items-center gap-x-[28px] gap-y-[12px] px-[24px] py-[20px]"
    >
      <div className="flex items-center gap-[10px]">
        <span aria-hidden className="bg-ok-text size-[10px] animate-pulse rounded-full" />
        <span className="text-text-sub text-[14px] font-semibold">지금 접속자</span>
      </div>
      <div className="flex items-baseline gap-[6px]">
        <span className="tracking-h1 text-[32px] font-extrabold">{num(data.last30Minutes)}</span>
        <span className="text-text-sub text-[14px]">명 · 최근 30분</span>
      </div>
      <span className="text-[15px] font-bold">최근 5분 {num(data.last5Minutes)}명</span>
      <span className="text-text-sub text-[14px]">
        {data.devices.map((d) => `${DEVICE_KO[d.name] ?? d.name} ${num(d.value)}`).join(" · ")}
      </span>
      <span className="text-text-sub ml-auto text-[13px]">
        GA 실시간 · 동의한 사람만 · 30초마다 새로 고쳐요
      </span>
    </section>
  );
}

/** 많이 본 공고: 공고 ID를 제목으로 바꿔 보여 줘요(못 찾으면 ID) */
function PopularNotices({ items }: { items: NoticeView[] }) {
  const { data: titles } = useNoticeTitles(items.map((i) => i.noticeId));
  if (items.length === 0) return <span className="text-text-sub text-[14px]">아직 없어요</span>;
  const max = Math.max(1, ...items.map((i) => i.views));
  return (
    <ol className="m-0 flex list-none flex-col gap-[10px] p-0">
      {items.map((i, rank) => (
        <li key={i.noticeId} className="flex flex-col gap-[4px]">
          <div className="flex items-baseline justify-between gap-[12px] text-[14px]">
            <Link
              href={routes.notice(i.noticeId)}
              target="_blank"
              className="text-text hover:text-text min-w-0 truncate font-semibold no-underline"
              title={titles?.[i.noticeId] ?? i.noticeId}
            >
              <span className="text-text-sub mr-[6px]">{rank + 1}</span>
              {titles?.[i.noticeId] ?? `공고 ${i.noticeId.slice(0, 8)}`}
            </Link>
            <span className="text-text-sub flex-none">
              {num(i.views)}회 · {num(i.users)}명
            </span>
          </div>
          <Bar share={(i.views / max) * 100} />
        </li>
      ))}
    </ol>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-card bg-surface flex flex-col gap-[8px] px-[24px] py-[22px]">
      <span className="text-text-sub text-[14px] font-semibold">{label}</span>
      <span className="tracking-h1 text-[32px] font-extrabold">{value}</span>
      <span className="text-text-sub text-[13px]">{note}</span>
    </div>
  );
}

function Card({
  title,
  desc,
  children,
}: {
  title: string;
  desc?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-card bg-surface flex min-w-0 flex-col gap-[14px] px-[24px] py-[22px]">
      <div className="flex flex-col gap-[2px]">
        <h2 className="m-0 text-[17px] font-extrabold">{title}</h2>
        {desc && <span className="text-text-sub text-[13px]">{desc}</span>}
      </div>
      {children}
    </section>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="grid gap-[14px]"
      style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}
    >
      {children}
    </div>
  );
}

function Bar({ share }: { share: number }) {
  return (
    <div className="bg-fill h-[10px] overflow-hidden rounded-[4px]">
      <div
        className="bg-brand h-full rounded-[4px]"
        style={{ width: `${Math.min(100, share)}%` }}
      />
    </div>
  );
}

function BarList({
  items,
  unit,
  label = (n) => n,
}: {
  items: TrafficItem[];
  unit: string;
  label?: (name: string) => string;
}) {
  if (items.length === 0) return <span className="text-text-sub text-[14px]">아직 없어요</span>;
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="m-0 flex list-none flex-col gap-[10px] p-0">
      {items.map((i) => (
        <li key={i.name} className="flex flex-col gap-[4px]">
          <div className="flex items-baseline justify-between gap-[12px] text-[14px]">
            <span className="min-w-0 truncate font-semibold" title={i.name}>
              {label(i.name)}
            </span>
            <span className="text-text-sub flex-none">
              {num(i.value)}
              {unit}
              {i.users !== i.value && ` · ${num(i.users)}명`}
            </span>
          </div>
          <Bar share={(i.value / max) * 100} />
        </li>
      ))}
    </ul>
  );
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  if (rows.length === 0) return <span className="text-text-sub text-[14px]">아직 없어요</span>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[14px]">
        <thead>
          <tr className="text-text-sub text-left text-[13px]">
            {head.map((h, i) => (
              <th
                key={h}
                className={cn(
                  "border-line border-b border-solid px-[10px] py-[8px] font-semibold whitespace-nowrap",
                  i > 0 && "text-right",
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={`${r[0]}-${ri}`} className="border-line-soft border-b border-solid">
              {r.map((c, ci) => (
                <td
                  key={ci}
                  className={cn("px-[10px] py-[8px] whitespace-nowrap", ci > 0 && "text-right")}
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AccessList({ items }: { items: BotAccess[] }) {
  if (items.length === 0) return <span className="text-text-sub text-[14px]">없어요</span>;
  return (
    <ul className="m-0 flex list-none flex-col p-0 text-[14px]">
      {items.map((a, i) => (
        <li
          key={`${a.at}-${i}`}
          className="border-line-soft flex flex-wrap items-baseline gap-x-[10px] gap-y-[2px] border-b border-solid py-[8px]"
        >
          <span className="text-text-sub w-[96px] flex-none">{when(a.at)}</span>
          <span className="font-semibold">
            {a.method} {a.path}
          </span>
          <span className={cn((a.status ?? 0) >= 400 ? "text-danger-text" : "text-text-sub")}>
            {a.status ?? "-"}
          </span>
          <span className="text-text-sub">{a.maskedIp ?? "IP 지움"}</span>
          <span className="text-text-sub">{CLIENT[a.client]?.label ?? a.client}</span>
        </li>
      ))}
    </ul>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-card bg-surface text-text-sub px-[24px] py-[40px] text-center text-[15px]">
      {text}
    </div>
  );
}
