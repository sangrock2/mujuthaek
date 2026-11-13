import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MScore } from "@/features/score/screens/MScore";
import { WebScore } from "@/features/score/screens/WebScore";

export const metadata: Metadata = { title: "청약 가점 계산 | 무주택자들" };

export default function ScorePage() {
  return <Responsive web={<WebScore />} mobile={<MScore />} />;
}
