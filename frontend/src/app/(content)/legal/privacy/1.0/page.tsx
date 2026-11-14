import type { Metadata } from "next";
import { PublishedLegalDocument } from "@/features/content/components/PublishedLegalDocument";
import { LEGAL_ORIGIN } from "@/features/content/legal/types";
import { privacyPolicy } from "@/features/content/legal/versions/v1";

export const metadata: Metadata = {
  title: "개인정보처리방침 v1.0 | 무주택자들",
  alternates: { canonical: `${LEGAL_ORIGIN}/legal/privacy/1.0` },
  robots: { index: false, follow: true },
};

export default function ArchivedPrivacyPage() {
  return <PublishedLegalDocument document={privacyPolicy} archived />;
}
