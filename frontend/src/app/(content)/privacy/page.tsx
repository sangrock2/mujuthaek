import type { Metadata } from "next";
import { PublishedLegalDocument } from "@/features/content/components/PublishedLegalDocument";
import { LEGAL_ORIGIN, privacyPolicy } from "@/features/content/legal/documents";

export const metadata: Metadata = {
  title: "개인정보처리방침 | 무주택자들",
  description: privacyPolicy.description,
  alternates: { canonical: `${LEGAL_ORIGIN}/privacy` },
  robots: { index: true, follow: true },
};

export default function PrivacyPage() {
  return <PublishedLegalDocument document={privacyPolicy} />;
}
