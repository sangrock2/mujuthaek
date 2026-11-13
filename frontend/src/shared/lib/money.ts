/** 원 단위 금액을 억 · 만 · 원으로 표시해요. */
export function formatWon(won: number): string {
  const amount = Math.round(Math.abs(won));
  const eok = Math.floor(amount / 100_000_000);
  const man = Math.floor((amount % 100_000_000) / 10_000);
  const rest = amount % 10_000;
  const parts: string[] = [];
  if (eok) parts.push(`${eok.toLocaleString("ko-KR")}억`);
  if (man) parts.push(`${man.toLocaleString("ko-KR")}만`);
  if (rest || !parts.length) parts.push(`${rest.toLocaleString("ko-KR")}원`);
  else parts[parts.length - 1] += " 원";
  return `${won < 0 ? "−" : ""}${parts.join(" ")}`;
}
