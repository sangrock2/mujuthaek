import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MBizSupport } from "@/screens/business/MBizSupport";
import { WebBizSupport } from "@/screens/business/WebBizSupport";

export const metadata: Metadata = { title: "사업 지원 | 무주택자들" };

export default function BizSupportPage() {
  return <Responsive web={<WebBizSupport />} mobile={<MBizSupport />} />;
}
