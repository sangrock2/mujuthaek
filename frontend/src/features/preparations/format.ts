export const noticeStatusLabels: Record<string, string> = {
  UPCOMING: "접수 예정",
  APPLYING: "접수 중",
  OPEN: "접수 중",
  ALWAYS: "상시 접수",
  CLOSED: "접수 마감",
};
export function scheduleTime(value: string | null | undefined) {
  if (!value) return "일시 확인 필요";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.replaceAll("-", ".");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
