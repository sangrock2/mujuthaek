import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MNotices } from "@/screens/content/MNotices";
import { WebNotices } from "@/screens/content/WebNotices";

export const metadata: Metadata = { title: "공지사항 | 무주택자들" };

export default function AnnouncementsPage() {
  return <Responsive web={<WebNotices />} mobile={<MNotices />} />;
}
