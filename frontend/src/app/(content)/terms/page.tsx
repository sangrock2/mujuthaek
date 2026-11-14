import type { Metadata } from "next";
import { PublishedLegalDocument } from "@/features/content/components/PublishedLegalDocument";
import { LEGAL_ORIGIN, serviceTerms } from "@/features/content/legal/documents";

export const metadata: Metadata = {
  title: "이용약관 | 무주택자들",
  description: serviceTerms.description,
  alternates: { canonical: `${LEGAL_ORIGIN}/terms` },
  robots: { index: true, follow: true },
};

export default function TermsPage() {
  return <PublishedLegalDocument document={serviceTerms} />;
}
