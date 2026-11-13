import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MWelcome } from "@/features/auth/screens/MWelcome";
import { WebWelcome } from "@/features/auth/screens/WebWelcome";

export const metadata: Metadata = { title: "가입 완료 | 무주택자들" };

export default function WelcomePage() {
  return <Responsive web={<WebWelcome />} mobile={<MWelcome />} />;
}
