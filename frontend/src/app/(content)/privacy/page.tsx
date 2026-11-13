import { USE_MOCKS } from "@/shared/lib/api/config";
import { LegalPending } from "@/features/content/components/LegalPending";
import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MPrivacy } from "@/features/content/screens/MPrivacy";
import { WebPrivacy } from "@/features/content/screens/WebPrivacy";

export const metadata: Metadata = { title: "개인정보처리방침 | 무주택자들" };

export default function PrivacyPage() {
  if (!USE_MOCKS) return <LegalPending title="개인정보처리방침" />;
  return <Responsive web={<WebPrivacy />} mobile={<MPrivacy />} />;
}
