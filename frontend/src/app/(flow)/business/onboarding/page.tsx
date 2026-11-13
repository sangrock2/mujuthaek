import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MBizOnboarding } from "@/features/business/screens/MBizOnboarding";
import { WebBizOnboarding } from "@/features/business/screens/WebBizOnboarding";

export const metadata: Metadata = { title: "사업 정보 입력 | 무주택자들" };

export default function BizOnboardingPage() {
  return <Responsive web={<WebBizOnboarding />} mobile={<MBizOnboarding />} />;
}
