"use client";

import { useAdminNotificationStats } from "@/features/admin/queries";
import { cn } from "@/lib/cn";
import type { NotificationStats } from "@/mocks/admin-notifications";

const TYPE_LABEL: Record<string, string> = {
  NEW_NOTICE: "새 공고",
  NEW_SUPPORT: "새 혜택·사업",
  DEADLINE_D3: "마감 3일 전",
  DEADLINE_D1: "마감 하루 전",
  CORRECTED: "정정 안내",
  FOLLOW_UP: "후속 안내",
  REPORT_ANSWERED: "제보 답변",
};

/** 알림 서버가 남기는 실패 코드 (모르는 코드는 그대로 보여요) */
const ERROR_LABEL: Record<string, string> = {
  PUSH_404: "구독이 없어짐 (기기에서 알림을 끄거나 앱을 지움)",
  PUSH_410: "구독이 없어짐 (기기에서 알림을 끄거나 앱을 지움)",
  PUSH_IO: "푸시 서비스에 연결하지 못함",
  PUSH_429: "푸시 서비스가 잠시 막음 (너무 많이 보냄)",
  PUSH_ENDPOINT_NOT_ALLOWED: "허용하지 않은 푸시 서비스 주소",
  PUSH_PAYLOAD_TOO_LARGE: "알림 내용이 너무 큼",
  PUSH_ADDRESS_UNREADABLE: "기기 정보를 읽지 못함",
  CHANNEL_UNAVAILABLE: "보낼 수단이 없음 (서버 설정)",
};

const pct = (n: number, d: number) => (d > 0 ? `${Math.round((n / d) * 100)}%` : "-");
const num = (n: number) => n.toLocaleString("ko-KR");

/** 종류별로 발송 결과(푸시)와 알림함 지표를 한 줄로 */
function rows(data: NotificationStats) {
  const types = new Set([
    ...data.engagement.map((e) => e.type),
    ...(data.delivery?.byType ?? []).map((d) => d.type),
  ]);
  return [...types].map((type) => {
    const e = data.engagement.find((x) => x.type === type);
    const push = data.delivery?.byType.find((x) => x.type === type && x.channel === "PUSH");
    return {
      type,
      created: e?.created ?? 0,
      shown: e?.shown ?? 0,
      read: e?.read ?? 0,
      clicked: e?.clicked ?? 0,
      sent: push?.sent ?? 0,
      failed: push?.failed ?? 0,
      pending: push?.pending ?? 0,
    };
  });
}

/** 트래픽 「알림」 탭: 보낸 알림이 잘 갔는지, 받은 회원이 보고 눌렀는지 (회원별 값 없이 합계만) */
export function NotificationPanel({ days }: { days: number }) {
  const { data, isPending, isError } = useAdminNotificationStats(days);
  const list = data ? rows(data) : [];
  const total = list.reduce(
    (t, r) => ({
      created: t.created + r.created,
      shown: t.shown + r.shown,
      read: t.read + r.read,
      clicked: t.clicked + r.clicked,
      sent: t.sent + r.sent,
      failed: t.failed + r.failed,
      pending: t.pending + r.pending,
    }),
    { created: 0, shown: 0, read: 0, clicked: 0, sent: 0, failed: 0, pending: 0 },
  );
  const delivered = !!data?.delivery;

  const cards = [
    { label: "받은 알림", value: num(total.created), sub: "알림함에 남긴 수" },
    {
      label: "푸시 발송 성공",
      value: delivered ? pct(total.sent, total.sent + total.failed) : "-",
      sub: delivered
        ? `성공 ${num(total.sent)} · 실패 ${num(total.failed)} · 대기 ${num(total.pending)}`
        : "알림 서버에 연결하지 못했어요",
      // 실패가 5%를 넘으면 눈에 띄게 (만료된 구독 몇 건은 늘 생겨요)
      tone: delivered && total.failed > (total.sent + total.failed) * 0.05 ? "warn" : undefined,
    },
    {
      label: "기기에 뜸",
      value: delivered ? pct(total.shown, total.sent) : "-",
      sub: `성공한 푸시 중 기기에 뜬 비율 · ${num(total.shown)}건`,
    },
    {
      label: "확인함",
      value: pct(total.read, total.created),
      sub: `받은 알림 중 읽은 비율 · ${num(total.read)}건`,
    },
    {
      label: "눌러서 이동",
      value: pct(total.clicked, total.created),
      sub: `받은 알림 중 눌러서 화면으로 간 비율 · ${num(total.clicked)}건`,
    },
  ];

  return (
    <>
      {isPending && <span className="text-text-sub text-[15px]">불러오는 중이에요</span>}
      {isError && <span className="text-text-sub text-[15px]">알림 지표를 불러오지 못했어요</span>}

      {data && (
        <>
          {!delivered && (
            <div
              role="status"
              className="rounded-control bg-check-bg text-check-text px-[16px] py-[12px] text-[14px] font-bold"
            >
              알림 서버에 연결하지 못해 발송 결과(성공·실패)는 보이지 않아요 · 알림함 지표만 보여요
            </div>
          )}

          <section aria-label="요약" className="grid grid-cols-2 gap-[12px] lg:grid-cols-5">
            {cards.map((c) => (
              <div
                key={c.label}
                className="rounded-card bg-surface flex flex-col gap-[6px] px-[20px] py-[18px]"
              >
                <span className="text-text-sub text-[14px] font-bold">{c.label}</span>
                <span
                  className={cn(
                    "text-[28px] font-extrabold",
                    c.tone === "warn" ? "text-danger-text" : "text-text",
                  )}
                >
                  {c.value}
                </span>
                <span className="text-text-sub text-[13px]">{c.sub}</span>
              </div>
            ))}
          </section>

          <section className="rounded-card bg-surface flex flex-col gap-[12px] px-[24px] py-[22px]">
            <h2 className="m-0 text-[18px] font-extrabold">종류별</h2>
            {list.length === 0 ? (
              <span className="text-text-sub py-[24px] text-center text-[15px]">
                이 기간에 보낸 알림이 없어요
              </span>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse text-[14px]">
                  <thead>
                    <tr className="text-text-sub text-left text-[13px]">
                      <th className="py-[8px] font-bold">종류</th>
                      <th className="py-[8px] text-right font-bold">받음</th>
                      <th className="py-[8px] text-right font-bold">푸시 성공</th>
                      <th className="py-[8px] text-right font-bold">실패</th>
                      <th className="py-[8px] text-right font-bold">대기</th>
                      <th className="py-[8px] text-right font-bold">기기에 뜸</th>
                      <th className="py-[8px] text-right font-bold">확인함</th>
                      <th className="py-[8px] text-right font-bold">눌러서 이동</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((r) => (
                      <tr key={r.type} className="border-t-line-soft border-t border-solid">
                        <td className="py-[10px] font-semibold">{TYPE_LABEL[r.type] ?? r.type}</td>
                        <td className="py-[10px] text-right">{num(r.created)}</td>
                        <td className="py-[10px] text-right">{delivered ? num(r.sent) : "-"}</td>
                        <td
                          className={cn(
                            "py-[10px] text-right",
                            r.failed > 0 && "text-danger-text font-bold",
                          )}
                        >
                          {delivered ? num(r.failed) : "-"}
                        </td>
                        <td className="py-[10px] text-right">{delivered ? num(r.pending) : "-"}</td>
                        <td className="py-[10px] text-right">
                          {num(r.shown)}{" "}
                          <span className="text-text-sub">({pct(r.shown, r.sent)})</span>
                        </td>
                        <td className="py-[10px] text-right">
                          {num(r.read)}{" "}
                          <span className="text-text-sub">({pct(r.read, r.created)})</span>
                        </td>
                        <td className="py-[10px] text-right">
                          {num(r.clicked)}{" "}
                          <span className="text-text-sub">({pct(r.clicked, r.created)})</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <span className="text-text-sub text-[13px]">
              기기에 뜸은 성공한 푸시 대비, 확인함·눌러서 이동은 받은 알림 대비예요. 확인함은 알림
              목록에서 읽었거나 눌러서 들어간 것이에요
            </span>
          </section>

          {delivered && (
            <section className="rounded-card bg-surface flex flex-col gap-[12px] px-[24px] py-[22px]">
              <h2 className="m-0 text-[18px] font-extrabold">실패 사유</h2>
              {data.delivery!.failures.length === 0 ? (
                <span className="text-text-sub text-[15px]">이 기간에 실패한 발송이 없어요</span>
              ) : (
                <ul className="m-0 flex list-none flex-col p-0">
                  {data.delivery!.failures.map((f) => (
                    <li
                      key={`${f.channel}-${f.error}`}
                      className="border-b-line-soft flex items-center gap-[12px] border-b border-solid py-[10px] text-[14px]"
                    >
                      <span className="rounded-tag bg-fill flex-none px-[8px] py-[2px] text-[12px] font-extrabold">
                        {f.channel === "PUSH" ? "푸시" : "이메일"}
                      </span>
                      <span className="min-w-0 flex-1">
                        {ERROR_LABEL[f.error] ?? f.error}
                        {ERROR_LABEL[f.error] && (
                          <span className="text-text-sub"> · {f.error}</span>
                        )}
                      </span>
                      <span className="flex-none font-bold">{num(f.count)}건</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </>
      )}
    </>
  );
}
