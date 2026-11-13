import { USE_MOCKS } from "@/shared/lib/api/config";
import { LegalPending } from "@/features/content/components/LegalPending";
import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MTerms } from "@/features/content/screens/MTerms";
import { WebTerms } from "@/features/content/screens/WebTerms";

export const metadata: Metadata = { title: "이용약관 | 무주택자들" };

export default function TermsPage() {
  if (!USE_MOCKS) return <LegalPending title="이용약관" />;
  return <Responsive web={<WebTerms />} mobile={<MTerms />} />;
}
