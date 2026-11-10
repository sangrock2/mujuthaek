import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MBenefits } from "@/screens/benefits/MBenefits";
import { WebBenefits } from "@/screens/benefits/WebBenefits";

export const metadata: Metadata = { title: "내 혜택 | 무주택자들" };

export default function BenefitsPage() {
  return <Responsive web={<WebBenefits />} mobile={<MBenefits />} />;
}
