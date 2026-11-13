import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MBusiness } from "@/features/business/screens/MBusiness";
import { WebBusiness } from "@/features/business/screens/WebBusiness";

export const metadata: Metadata = { title: "사업공간 | 무주택자들" };

export default function BusinessPage() {
  return <Responsive web={<WebBusiness />} mobile={<MBusiness />} />;
}
