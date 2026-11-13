import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MNotices } from "@/features/content/screens/MNotices";
import { WebNotices } from "@/features/content/screens/WebNotices";

export const metadata: Metadata = { title: "공지사항 | 무주택자들" };

export default function AnnouncementsPage() {
  return <Responsive web={<WebNotices />} mobile={<MNotices />} />;
}
