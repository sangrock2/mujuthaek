/** Public upstreams must use TLS. Plain HTTP is only for local development/E2E. */
export function secureApiOrigin(value: string | undefined, hosted = false): string {
  if (!value) return "";
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("API 주소는 올바른 HTTPS origin이어야 합니다.");
  }
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash ||
    !(url.protocol === "https:" || (!hosted && loopback && url.protocol === "http:")) ||
    (hosted && loopback)
  ) {
    throw new Error("API 주소는 HTTPS origin이어야 합니다. HTTP는 로컬 loopback에서만 허용합니다.");
  }
  return url.origin;
}
