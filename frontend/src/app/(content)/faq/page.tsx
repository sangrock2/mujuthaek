import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MFaq } from "@/features/content/screens/MFaq";
import { WebFaq } from "@/features/content/screens/WebFaq";

export const metadata: Metadata = { title: "자주 묻는 질문 | 무주택자들" };

export default function FaqPage() {
  return <Responsive web={<WebFaq />} mobile={<MFaq />} />;
}
