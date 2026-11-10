import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MFaq } from "@/screens/content/MFaq";
import { WebFaq } from "@/screens/content/WebFaq";

export const metadata: Metadata = { title: "자주 묻는 질문 | 무주택자들" };

export default function FaqPage() {
  return <Responsive web={<WebFaq />} mobile={<MFaq />} />;
}
