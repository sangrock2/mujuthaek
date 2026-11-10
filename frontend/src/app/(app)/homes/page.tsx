import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MHomes } from "@/screens/homes/MHomes";
import { WebHomes } from "@/screens/homes/WebHomes";

export const metadata: Metadata = { title: "내 집 | 무주택자들" };

export default function HomesPage() {
  return <Responsive web={<WebHomes />} mobile={<MHomes />} />;
}
