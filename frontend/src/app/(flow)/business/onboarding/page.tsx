import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MBizOnboarding } from "@/screens/business/MBizOnboarding";
import { WebBizOnboarding } from "@/screens/business/WebBizOnboarding";

export const metadata: Metadata = { title: "사업 정보 입력 | 무주택자들" };

export default function BizOnboardingPage() {
  return <Responsive web={<WebBizOnboarding />} mobile={<MBizOnboarding />} />;
}
