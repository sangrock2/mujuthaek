import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MLogin } from "@/screens/auth/MLogin";
import { WebLogin } from "@/screens/auth/WebLogin";

export const metadata: Metadata = { title: "로그인 | 무주택자들" };

export default function LoginPage() {
  return <Responsive web={<WebLogin />} mobile={<MLogin />} />;
}
