import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MSignup } from "@/features/auth/screens/MSignup";
import { WebSignup } from "@/features/auth/screens/WebSignup";

export const metadata: Metadata = { title: "가입 마무리 | 무주택자들", robots: { index: false } };

export default function SignupPage() {
  return <Responsive web={<WebSignup />} mobile={<MSignup />} />;
}
