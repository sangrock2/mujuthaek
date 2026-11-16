// 서버·수집한 글에서 온 주소를 링크·새 창·화면 이동에 쓰기 전에 확인해요 (2026-11-16 보안 감사 L-4)
// React 19는 javascript:만 막고 data:·search-ms:·ms-*:·intent: 같은 주소는 그대로 열어요. window.open·location은 그마저 막지 않아요

/** 링크로 받을 주소 길이 상한. 기관 주소는 보통 수백 자 안이에요 */
export const MAX_URL_LENGTH = 2048;

/**
 * 주소에 있으면 안 되는 글자: 제어 문자(C0·DEL·C1), 공백(전각·폭 없는 공백 포함), 글 방향을 바꾸는 문자, 역슬래시.
 * 브라우저는 주소 속 탭·줄바꿈을 지우고 역슬래시를 「/」로 읽어서, 검사한 주소와 실제로 열리는 주소가 달라질 수 있어요
 */
const UNSAFE_CHARS =
  /[\u0000-\u0020\u007f-\u00a0\u00ad\u1680\u180e\u2000-\u200f\u2028-\u202f\u205f-\u206f\u3000\ufeff\\]/;

/**
 * 외부 링크로 열어도 되는 주소면 정리한 주소(URL.href)를, 아니면 null을 돌려줘요.
 * - 절대 주소의 http:·https:만 (상대 주소·「//」로 시작하는 주소·다른 스킴은 안 돼요)
 * - 아이디·비밀번호가 붙은 주소(https://user:pass@host)는 안 돼요 (진짜 목적지를 속이는 데 써요)
 * - 제어 문자·공백·역슬래시가 있거나 너무 길면 안 돼요 (앞뒤 공백만 지워요)
 */
export function safeExternalUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text || text.length > MAX_URL_LENGTH || UNSAFE_CHARS.test(text)) return null;
  if (!/^https?:\/\/[^/]/i.test(text)) return null;
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  if (url.username || url.password || !url.hostname) return null;
  return url.href;
}

/** 앱 안 경로인지 볼 때 붙여 보는 가짜 출처 (실제로 요청하지 않아요) */
const PROBE_ORIGIN = "https://app.invalid";

/**
 * 이 사이트 안에서 이동할 경로면 그대로, 아니면 null을 돌려줘요. 서버가 준 linkPath처럼 next/link·router.push·location에 넣는 값에 써요.
 * 「/」로 시작해야 하고 「//다른곳」·「/\다른곳」(다른 사이트로 가요)이나 제어 문자·공백·역슬래시가 있으면 안 돼요
 */
export function safeAppPath(value: unknown): string | null {
  if (typeof value !== "string" || !value || value.length > MAX_URL_LENGTH) return null;
  if (!value.startsWith("/") || value.startsWith("//") || UNSAFE_CHARS.test(value)) return null;
  try {
    return new URL(value, PROBE_ORIGIN).origin === PROBE_ORIGIN ? value : null;
  } catch {
    return null;
  }
}
