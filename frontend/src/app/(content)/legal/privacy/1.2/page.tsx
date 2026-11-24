import type { Metadata } from "next";
import { PublishedLegalDocument } from "@/features/content/components/PublishedLegalDocument";
import { privacyPolicy } from "@/features/content/legal/versions/v1_2";

export const metadata: Metadata = {
  title: "개인정보처리방침 v1.2 | 무주택자들",
  robots: { index: false, follow: true },
};

export default function Page() {
  return <PublishedLegalDocument document={privacyPolicy} archived />;
}
