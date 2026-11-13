import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MBenefits } from "@/features/benefits/screens/MBenefits";
import { WebBenefits } from "@/features/benefits/screens/WebBenefits";

export const metadata: Metadata = { title: "내 혜택 | 무주택자들" };

export default function BenefitsPage() {
  return <Responsive web={<WebBenefits />} mobile={<MBenefits />} />;
}
