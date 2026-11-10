import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MHome } from "@/screens/home/MHome";
import { WebHome } from "@/screens/home/WebHome";

export const metadata: Metadata = { title: "홈 | 무주택자들" };

export default function HomePage() {
  return <Responsive web={<WebHome />} mobile={<MHome />} />;
}
