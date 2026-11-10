"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { loadKakaoMaps, type KakaoMap, type KakaoMaps } from "@/lib/kakao-map";
import type { NoticeSite } from "@/mocks/notice";

type Props = {
  sites: NoticeSite[];
  /** 고른 집의 단지 (강조하고 가운데로) */
  selectedSiteId?: string;
  onSelectSite?: (siteId: string) => void;
  className?: string;
};

const pin =
  "rounded-pill cursor-pointer border-0 px-[10px] py-[6px] text-[13px] font-extrabold whitespace-nowrap shadow-[0_4px_10px_rgba(25,31,40,0.2)]";

/** 공고 단지·건물 위치 (카카오맵). 호마다 좌표가 없어서 단지 단위로 보여줘요 */
export function SitesMap({ sites, selectedSiteId, onSelectSite, className }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [maps, setMaps] = useState<KakaoMaps | null>(null);
  const [map, setMap] = useState<KakaoMap | null>(null);
  const [failed, setFailed] = useState(false);
  const located = useMemo(() => sites.filter((s) => s.lat !== null && s.lng !== null), [sites]);
  const focus = located.find((s) => s.id === selectedSiteId) ?? located[0];

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

  // 지도는 한 번만 만들고, 처음엔 모든 단지가 보이게 맞춰요
  useEffect(() => {
    if (!maps || !box.current || located.length === 0) return;
    const m = new maps.Map(box.current, {
      center: new maps.LatLng(located[0].lat!, located[0].lng!),
      level: 4,
    });
    if (located.length > 1) {
      const bounds = new maps.LatLngBounds();
      located.forEach((s) => bounds.extend(new maps.LatLng(s.lat!, s.lng!)));
      m.setBounds(bounds);
    }
    setMap(m);
  }, [maps, located]);

  // 고른 단지로 옮기기
  useEffect(() => {
    if (maps && map && focus) map.panTo(new maps.LatLng(focus.lat!, focus.lng!));
  }, [maps, map, focus]);

  // 단지 표시
  useEffect(() => {
    if (!maps || !map) return;
    const overlays = located.map((s) => {
      const el = document.createElement("button");
      el.type = "button";
      el.textContent = s.lifeScore === undefined ? s.name : `${s.name} · ${s.lifeScore}점`;
      el.setAttribute(
        "aria-label",
        s.lifeScore === undefined ? `${s.name} 위치` : `${s.name} 위치 · 생활권 ${s.lifeScore}점`,
      );
      el.className = cn(pin, s.id === focus?.id ? "bg-brand text-white" : "bg-surface text-text");
      el.addEventListener("click", () => onSelectSite?.(s.id));
      return new maps.CustomOverlay({
        position: new maps.LatLng(s.lat!, s.lng!),
        content: el,
        yAnchor: 1,
        clickable: true,
        zIndex: s.id === focus?.id ? 2 : 1,
      });
    });
    overlays.forEach((o) => o.setMap(map));
    return () => overlays.forEach((o) => o.setMap(null));
  }, [maps, map, located, focus, onSelectSite]);

  return (
    <div className={cn("bg-placeholder-bg relative overflow-hidden rounded-[20px]", className)}>
      <div ref={box} aria-label="단지 위치 지도" className="absolute inset-0" />
      {(failed || !focus) && (
        <p className="text-text-sub absolute inset-0 m-0 flex items-center justify-center px-[24px] text-center text-[14px]">
          {failed ? "지도를 불러오지 못했어요" : "단지 위치를 아직 찾지 못했어요"}
        </p>
      )}
    </div>
  );
}
