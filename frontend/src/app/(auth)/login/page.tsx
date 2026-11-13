import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MLogin } from "@/features/auth/screens/MLogin";
import { WebLogin } from "@/features/auth/screens/WebLogin";

export const metadata: Metadata = { title: "로그인 | 무주택자들" };

export default function LoginPage() {
  return <Responsive web={<WebLogin />} mobile={<MLogin />} />;
}
