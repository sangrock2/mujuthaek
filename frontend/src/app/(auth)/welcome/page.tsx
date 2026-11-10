import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MWelcome } from "@/screens/auth/MWelcome";
import { WebWelcome } from "@/screens/auth/WebWelcome";

export const metadata: Metadata = { title: "가입 완료 | 무주택자들" };

export default function WelcomePage() {
  return <Responsive web={<WebWelcome />} mobile={<MWelcome />} />;
}
