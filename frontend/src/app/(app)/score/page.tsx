import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MScore } from "@/screens/score/MScore";
import { WebScore } from "@/screens/score/WebScore";

export const metadata: Metadata = { title: "청약 가점 계산 | 무주택자들" };

export default function ScorePage() {
  return <Responsive web={<WebScore />} mobile={<MScore />} />;
}
