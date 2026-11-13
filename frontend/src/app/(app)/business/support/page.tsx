import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MBizSupport } from "@/features/business/screens/MBizSupport";
import { WebBizSupport } from "@/features/business/screens/WebBizSupport";

export const metadata: Metadata = { title: "사업 지원 | 무주택자들" };

export default function BizSupportPage() {
  return <Responsive web={<WebBizSupport />} mobile={<MBizSupport />} />;
}
