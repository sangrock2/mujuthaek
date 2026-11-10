import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MAlerts } from "@/screens/alerts/MAlerts";
import { WebAlerts } from "@/screens/alerts/WebAlerts";

export const metadata: Metadata = { title: "알림 | 무주택자들" };

export default function AlertsPage() {
  return <Responsive web={<WebAlerts />} mobile={<MAlerts />} />;
}
