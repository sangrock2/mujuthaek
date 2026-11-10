import { Suspense } from "react";
import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { supportList } from "@/mocks/business";
import { MSupportDetail } from "@/screens/business/MSpaceDetail";
import { WebSupportDetail } from "@/screens/business/WebSpaceDetail";

type Params = { params: Promise<{ id: string }> };

export const metadata: Metadata = { title: "사업 지원 상세 | 무주택자들" };

export function generateStaticParams() {
  return supportList.items.map((s) => ({ id: s.id }));
}

/** 사업 지원 하나: 상세 API가 없어서 판정 응답으로 보여줘요 (화면은 공간 상세와 같아요) */
async function SupportDetail({ params }: Params) {
  const { id } = await params;
  return <Responsive web={<WebSupportDetail id={id} />} mobile={<MSupportDetail id={id} />} />;
}

// params는 Suspense 안에서 읽어요 (Cache Components)
export default function SupportDetailPage({ params }: Params) {
  return (
    <Suspense>
      <SupportDetail params={params} />
    </Suspense>
  );
}
