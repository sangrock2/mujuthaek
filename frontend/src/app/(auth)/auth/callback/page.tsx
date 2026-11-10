import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthCallback } from "@/screens/auth/AuthCallback";

export const metadata: Metadata = { title: "로그인 | 무주택자들", robots: { index: false } };

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={null}>
      <AuthCallback />
    </Suspense>
  );
}
