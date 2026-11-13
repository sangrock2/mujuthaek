import type { Metadata } from "next";
import { Suspense } from "react";
import { Responsive } from "@/shared/layout/Responsive";
import { PreparationDetail } from "@/features/preparations/PreparationDetail";

export const metadata: Metadata = {
  title: "신청 준비함 | 무주택자들",
  robots: { index: false, follow: false },
};
export default function PreparationPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={null}>
      <Detail params={params} />
    </Suspense>
  );
}
async function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Responsive web={<PreparationDetail id={id} />} mobile={<PreparationDetail id={id} mobile />} />
  );
}
