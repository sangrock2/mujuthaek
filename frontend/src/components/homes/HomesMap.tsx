"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { ListingVerdict } from "@/components/ui/Badge";
import { useHomes } from "@/features/homes/queries";
import {
  initialCenter,
  pinLabel,
  useNoticeMap,
  type MapView,
  type NoticeMapResponse,
  type PinTone,
} from "@/features/homes/map";
import { USE_MOCKS } from "@/lib/api/config";
import { cn } from "@/lib/cn";
import { loadKakaoMaps, type KakaoMap, type KakaoMaps, type KakaoOverlay } from "@/lib/kakao-map";
import { routes } from "@/lib/routes";
import type { HomeMapPin } from "@/mocks/homes";

type Props = {
  /** 처음 보여줄 지역 (찾아볼 지역) */
  regionCodes: string[];
  tenure: "RENT" | "BUY";
  /** 맞춤 목록에서 받은 공고별 판정 */
  verdictOf: (id: string) => ListingVerdict | undefined;
  className?: string;
};

const pinClass: Record<PinTone, string> = {
  ok: "bg-brand text-white",
  check: "bg-surface text-check-text",
  no: "bg-surface text-text-tertiary",
  unknown: "bg-surface text-text",
};

const pinBase =
  "rounded-pill cursor-pointer border-0 px-[10px] py-[6px] text-[13px] font-extrabold whitespace-nowrap shadow-[0_4px_10px_rgba(25,31,40,0.2)]";

/** 공고 핀: 제목 + 종류·마감 두 줄 */
const noticePin =
  "flex max-w-[200px] cursor-pointer flex-col items-start gap-[1px] rounded-[12px] border-0 px-[10px] py-[6px] text-left shadow-[0_4px_10px_rgba(25,31,40,0.2)]";

const panel = "rounded-card bg-placeholder-bg relative overflow-hidden";

/** 지도 위 버튼 하나 (카카오 CustomOverlay 내용). 둘째 줄이 있으면 작게 */
function overlayButton(
  lines: [string, string?],
  className: string,
  label: string,
  onClick: () => void,
) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = className;
  const [main, sub] = lines;
  if (sub === undefined) el.textContent = main;
  else {
    const title = document.createElement("span");
    title.className = "block max-w-full truncate text-[13px] font-extrabold";
    title.textContent = main;
    const meta = document.createElement("span");
    meta.className = "block text-[11px] font-bold whitespace-nowrap opacity-80";
    meta.textContent = sub;
    el.append(title, meta);
  }
  el.setAttribute("aria-label", label);
  el.addEventListener("click", onClick);
  return el;
}

/** 실제 지도: 카카오맵 + GET /notices/map. 움직임을 멈추면 그 범위를 다시 받아요 */
function KakaoHomesMap({ regionCodes, tenure, verdictOf, className }: Props) {
  const router = useRouter();
  const box = useRef<HTMLDivElement>(null);
  const [maps, setMaps] = useState<KakaoMaps | null>(null);
  const [map, setMap] = useState<KakaoMap | null>(null);
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState<MapView | null>(null);
  const q = useNoticeMap(view, tenure);
  // 처음 연 지역만 써요 (지역을 바꿔도 사용자가 옮긴 지도는 그대로)
  const [start] = useState(() => initialCenter(regionCodes));

  useEffect(() => {
    let alive = true;
    loadKakaoMaps().then(
      (k) => alive && setMaps(k),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!maps || !box.current) return;
    const m = new maps.Map(box.current, {
      center: new maps.LatLng(start.lat, start.lng),
      level: start.level,
    });
    const onIdle = () => {
      const b = m.getBounds();
      const sw = b.getSouthWest();
      const ne = b.getNorthEast();
      setView({
        swLat: sw.getLat(),
        swLng: sw.getLng(),
        neLat: ne.getLat(),
        neLng: ne.getLng(),
        level: m.getLevel(),
      });
    };
    maps.event.addListener(m, "idle", onIdle);
    onIdle();
    setMap(m);
    return () => maps.event.removeListener(m, "idle", onIdle);
  }, [maps, start]);

  // 핀 · 묶음 다시 그리기
  const data: NoticeMapResponse | undefined = q.data;
  useEffect(() => {
    if (!maps || !map || !data) return;
    const overlays: KakaoOverlay[] = [
      ...data.pins.map((p) => {
        const tone: PinTone = verdictOf(p.id) ?? "unknown";
        return new maps.CustomOverlay({
          position: new maps.LatLng(p.lat, p.lng),
          content: overlayButton(
            [p.title, pinLabel(p)],
            cn(noticePin, pinClass[tone]),
            `${p.title}, ${pinLabel(p)}`,
            () => router.push(routes.notice(p.id)),
          ),
          yAnchor: 1,
          clickable: true,
          zIndex: tone === "ok" ? 3 : tone === "check" ? 2 : 1,
        });
      }),
      ...data.clusters.map((c) => {
        const at = new maps.LatLng(c.lat, c.lng);
        const name = c.regionName ?? "지역 미확인";
        return new maps.CustomOverlay({
          position: at,
          content: overlayButton(
            [`${name} ${c.count}`],
            cn(pinBase, "bg-text text-white"),
            `${name} 공고 ${c.count}곳, 눌러서 가까이 보기`,
            () => map.setLevel(Math.max(1, map.getLevel() - 3), { anchor: at, animate: true }),
          ),
          clickable: true,
        });
      }),
    ];
    overlays.forEach((o) => o.setMap(map));
    return () => overlays.forEach((o) => o.setMap(null));
  }, [maps, map, data, verdictOf, router]);

  const count = data ? data.pins.length + data.clusters.reduce((n, c) => n + c.count, 0) : null;

  return (
    <div className={cn(panel, className)}>
      <div ref={box} aria-label="공고 위치 지도" className="absolute inset-0" />
      {failed && (
        <p className="text-text-sub absolute inset-0 m-0 flex items-center justify-center px-[24px] text-center text-[15px]">
          지도를 불러오지 못했어요. 목록으로 봐 주세요
        </p>
      )}
      {!failed && (
        <span
          aria-live="polite"
          className="rounded-pill bg-surface text-text-sub pointer-events-none absolute top-[10px] left-[10px] z-[5] px-[12px] py-[6px] text-[13px] font-bold shadow-[0_2px_6px_rgba(25,31,40,0.12)]"
        >
          {q.isError
            ? "공고 위치를 불러오지 못했어요"
            : count === null
              ? "공고 위치를 불러오는 중이에요"
              : count === 0
                ? "이 범위에는 공고가 없어요"
                : `이 범위 공고 ${count}곳`}
        </span>
      )}
    </div>
  );
}

const mockTone: Record<HomeMapPin["tone"], string> = {
  brand: pinClass.ok,
  plain: pinClass.unknown,
  check: pinClass.check,
};

/** 목업: 그림 위에 예시 핀 */
function MockHomesMap({ verdictOf, className }: Props) {
  const { data } = useHomes();
  return (
    <div aria-label="공고 위치 지도" role="img" className={cn(panel, className)}>
      <span
        aria-hidden
        className="bg-map-water absolute top-[44%] left-[-20px] h-[26px] w-[120%] rotate-[-8deg]"
      />
      <span
        aria-hidden
        className="bg-map-park-2 absolute top-[12%] left-[8%] h-[70px] w-[90px] rounded-[18px]"
      />
      {data.mapPins
        .filter((p) => verdictOf(p.id) !== undefined)
        .map((p) => (
          <span
            key={p.id}
            className={cn(pinBase, "absolute cursor-default", mockTone[p.tone])}
            style={{ left: p.left, top: p.top }}
          >
            {p.label}
          </span>
        ))}
    </div>
  );
}

// USE_MOCKS는 빌드 때 정해지는 값이라 바뀌지 않아요
export const HomesMap = USE_MOCKS ? MockHomesMap : KakaoHomesMap;
