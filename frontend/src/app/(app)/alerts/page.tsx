import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MAlerts } from "@/features/alerts/screens/MAlerts";
import { WebAlerts } from "@/features/alerts/screens/WebAlerts";

export const metadata: Metadata = { title: "알림 | 무주택자들" };

export default function AlertsPage() {
  return <Responsive web={<WebAlerts />} mobile={<MAlerts />} />;
}
