import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MHomes } from "@/features/homes/screens/MHomes";
import { WebHomes } from "@/features/homes/screens/WebHomes";

export const metadata: Metadata = { title: "내 집 | 무주택자들" };

export default function HomesPage() {
  return <Responsive web={<WebHomes />} mobile={<MHomes />} />;
}
