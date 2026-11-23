import type { Metadata } from "next";
import { EmailAction } from "@/features/me/components/EmailAction";
export const metadata: Metadata = {
  title: "이메일 알림 동의 철회 | 무주택자들",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};
export default function Page() {
  return <EmailAction action="unsubscribe" />;
}
