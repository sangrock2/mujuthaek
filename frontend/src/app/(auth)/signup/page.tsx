import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MSignup } from "@/features/auth/screens/MSignup";
import { WebSignup } from "@/features/auth/screens/WebSignup";
import { privacyPolicy, serviceTerms } from "@/features/content/legal/documents";

export const metadata: Metadata = { title: "가입 마무리 | 무주택자들", robots: { index: false } };

export default function SignupPage() {
  // 동의 화면이 링크하는 지금 문서(/terms · /privacy)의 버전을 동의 기록에 보내요.
  // 서버에서 읽어 버전만 넘겨서 약관 전문이 브라우저 번들에 들어가지 않아요
  const versions = { terms: serviceTerms.version, privacy: privacyPolicy.version };
  return (
    <Responsive web={<WebSignup versions={versions} />} mobile={<MSignup versions={versions} />} />
  );
}
