import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MPrivacy } from "@/screens/content/MPrivacy";
import { WebPrivacy } from "@/screens/content/WebPrivacy";

export const metadata: Metadata = { title: "개인정보처리방침 | 무주택자들" };

export default function PrivacyPage() {
  return <Responsive web={<WebPrivacy />} mobile={<MPrivacy />} />;
}
