import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MHome } from "@/features/home/screens/MHome";
import { WebHome } from "@/features/home/screens/WebHome";

export const metadata: Metadata = { title: "홈 | 무주택자들" };

export default function HomePage() {
  return <Responsive web={<WebHome />} mobile={<MHome />} />;
}
