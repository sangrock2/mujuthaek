// API 경로에 값(ID 등)을 넣는 도우미 (2026-11-16 보안 감사 L-6)
// 인코딩하지 않으면 「../users?size=1」 같은 값이 다른 API를 관리자 토큰으로 부르게 돼요

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** UUID 모양인지. 주소의 ?job= 같은 값을 API 경로에 넣기 전에 봐요 */
export const isUuid = (value: unknown): value is string =>
  typeof value === "string" && UUID.test(value);

/**
 * 경로 한 칸에 넣을 값. 인코딩해서 「/」「?」「#」「%」가 경로를 바꾸지 못하게 해요.
 * 빈 값·「.」·「..」은 인코딩해도 브라우저가 경로를 줄여서(한 칸 위로) 다른 API를 부르게 되니 거부해요
 */
export function pathSegment(value: string | number): string {
  const text = String(value);
  if (text === "" || text === "." || text === "..") {
    throw new Error("API 경로에 넣을 수 없는 값이에요");
  }
  return encodeURIComponent(text);
}

/** 템플릿의 ${값}마다 {@link pathSegment}를 써서 경로를 만들어요. 예: apiPath`/api/admin/users/${id}/role` */
export function apiPath(strings: TemplateStringsArray, ...values: (string | number)[]): string {
  return strings.reduce(
    (path, part, i) => path + part + (i < values.length ? pathSegment(values[i]) : ""),
    "",
  );
}
