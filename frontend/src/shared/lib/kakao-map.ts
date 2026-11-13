// 카카오맵 JavaScript SDK를 한 번만 불러와요. 키는 카카오 개발자 콘솔 > 앱 키 > JavaScript 키
// (플랫폼 > Web에 사이트 도메인을 등록해야 지도가 떠요)

export const KAKAO_MAP_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY ?? "";

/** 쓰는 부분만 적은 카카오맵 타입 */
export type KakaoLatLng = { getLat(): number; getLng(): number };
export type KakaoBounds = { getSouthWest(): KakaoLatLng; getNorthEast(): KakaoLatLng };
export type KakaoMap = {
  getBounds(): KakaoBounds;
  getLevel(): number;
  setLevel(level: number, options?: { anchor?: KakaoLatLng; animate?: boolean }): void;
  setCenter(latLng: KakaoLatLng): void;
  panTo(latLng: KakaoLatLng): void;
  setBounds(bounds: KakaoLatLngBounds): void;
  relayout(): void;
};
export type KakaoLatLngBounds = { extend(latLng: KakaoLatLng): void };
export type KakaoOverlay = { setMap(map: KakaoMap | null): void };
export type KakaoMaps = {
  load(callback: () => void): void;
  LatLng: new (lat: number, lng: number) => KakaoLatLng;
  LatLngBounds: new () => KakaoLatLngBounds;
  Map: new (container: HTMLElement, options: { center: KakaoLatLng; level: number }) => KakaoMap;
  CustomOverlay: new (options: {
    position: KakaoLatLng;
    content: HTMLElement;
    yAnchor?: number;
    clickable?: boolean;
    zIndex?: number;
  }) => KakaoOverlay;
  event: {
    addListener(target: KakaoMap, type: "idle", handler: () => void): void;
    removeListener(target: KakaoMap, type: "idle", handler: () => void): void;
  };
};

declare global {
  interface Window {
    kakao?: { maps: KakaoMaps };
  }
}

let loading: Promise<KakaoMaps> | null = null;

/** SDK를 불러와 kakao.maps를 돌려줘요. 키가 없거나 못 불러오면 실패해요 */
export function loadKakaoMaps(): Promise<KakaoMaps> {
  if (!KAKAO_MAP_KEY) return Promise.reject(new Error("NEXT_PUBLIC_KAKAO_MAP_KEY가 없어요"));
  if (loading) return loading;
  loading = new Promise<KakaoMaps>((resolve, reject) => {
    const ready = () => window.kakao!.maps.load(() => resolve(window.kakao!.maps));
    if (window.kakao?.maps) return ready();
    const script = document.createElement("script");
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(KAKAO_MAP_KEY)}&autoload=false`;
    script.async = true;
    script.onload = () => (window.kakao?.maps ? ready() : reject(new Error("카카오맵 SDK 없음")));
    script.onerror = () => reject(new Error("카카오맵 SDK를 불러오지 못했어요"));
    document.head.appendChild(script);
  }).catch((e) => {
    loading = null; // 다음에 다시 시도해요
    throw e;
  });
  return loading;
}
