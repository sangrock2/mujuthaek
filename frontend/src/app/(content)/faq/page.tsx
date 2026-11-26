import type { Metadata } from "next";
import { FaqScreen } from "@/features/content/screens/FaqScreen";

export const metadata: Metadata = { title: "자주 묻는 질문 | 무주택자들" };

export default function FaqPage() {
  return <FaqScreen />;
}
