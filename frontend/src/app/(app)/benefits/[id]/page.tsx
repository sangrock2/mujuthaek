import { detailMetadata } from "@/shared/lib/detail-metadata";
import { Suspense } from "react";
import { Responsive } from "@/shared/layout/Responsive";
import { benefitsSummary } from "@/features/benefits/mocks/benefits";
import { MBenefitDetail } from "@/features/benefits/screens/MBenefitDetail";
import { WebBenefits } from "@/features/benefits/screens/WebBenefits";

type Params = { params: Promise<{ id: string }> };

export function generateStaticParams() {
  return benefitsSummary.items.map((b) => ({ id: b.id }));
}

// 혜택 이름은 화면에서 API로 받아요. 목업 이름이 탭 제목에 나오지 않게 공고 상세처럼 고정 제목을 써요
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return detailMetadata("benefits", id);
}

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
