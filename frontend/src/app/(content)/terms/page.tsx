import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MTerms } from "@/screens/content/MTerms";
import { WebTerms } from "@/screens/content/WebTerms";

export const metadata: Metadata = { title: "이용약관 | 무주택자들" };

export default function TermsPage() {
  return <Responsive web={<WebTerms />} mobile={<MTerms />} />;
}
