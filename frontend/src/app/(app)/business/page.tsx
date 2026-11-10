import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MBusiness } from "@/screens/business/MBusiness";
import { WebBusiness } from "@/screens/business/WebBusiness";

export const metadata: Metadata = { title: "사업공간 | 무주택자들" };

export default function BusinessPage() {
  return <Responsive web={<WebBusiness />} mobile={<MBusiness />} />;
}
