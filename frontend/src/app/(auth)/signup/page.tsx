import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MSignup } from "@/screens/auth/MSignup";
import { WebSignup } from "@/screens/auth/WebSignup";

export const metadata: Metadata = { title: "가입 마무리 | 무주택자들", robots: { index: false } };

export default function SignupPage() {
  return <Responsive web={<WebSignup />} mobile={<MSignup />} />;
}
