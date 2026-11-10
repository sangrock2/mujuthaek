import { Suspense } from "react";
import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { benefitsSummary } from "@/mocks/benefits";
import { MBenefitDetail } from "@/screens/benefits/MBenefitDetail";
import { WebBenefits } from "@/screens/benefits/WebBenefits";

type Params = { params: Promise<{ id: string }> };

export function generateStaticParams() {
  return benefitsSummary.items.map((b) => ({ id: b.id }));
}

// 혜택 이름은 화면에서 API로 받아요. 목업 이름이 탭 제목에 나오지 않게 공고 상세처럼 고정 제목을 써요
export const metadata: Metadata = { title: "혜택 상세 | 무주택자들" };

async function BenefitDetail({ params }: Params) {
  const { id } = await params;
  return <Responsive web={<WebBenefits initialId={id} />} mobile={<MBenefitDetail id={id} />} />;
}

export default function BenefitDetailPage({ params }: Params) {
  return (
    <Suspense>
      <BenefitDetail params={params} />
    </Suspense>
  );
}
