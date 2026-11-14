import type { Metadata } from "next";
import { PublishedLegalDocument } from "@/features/content/components/PublishedLegalDocument";
import { LEGAL_ORIGIN } from "@/features/content/legal/types";
import { serviceTerms } from "@/features/content/legal/versions/v1";

export const metadata: Metadata = {
  title: "이용약관 v1.0 | 무주택자들",
  alternates: { canonical: `${LEGAL_ORIGIN}/legal/terms/1.0` },
  robots: { index: false, follow: true },
};

export default function ArchivedTermsPage() {
  return <PublishedLegalDocument document={serviceTerms} archived />;
}
