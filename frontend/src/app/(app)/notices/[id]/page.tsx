import type { Metadata } from "next";
import { Suspense } from "react";
import { Responsive } from "@/components/layout/Responsive";
import { USE_MOCKS } from "@/lib/api/config";
import { notices } from "@/mocks/notice";
import { MDetail } from "@/screens/notice/MDetail";
import { MDetailUnits } from "@/screens/notice/MDetailUnits";
import { WebDetail } from "@/screens/notice/WebDetail";
import { WebDetailUnits } from "@/screens/notice/WebDetailUnits";

export const metadata: Metadata = { title: "공고 상세 | 무주택자들" };

export function generateStaticParams() {
  return notices.map((n) => ({ id: n.id }));
}

type Params = Promise<{ id: string }>;

export default function NoticePage({ params }: { params: Params }) {
  // params는 Suspense 안에서 읽어야 이동이 바로 그려져요
  return (
    <Suspense fallback={null}>
      <NoticeDetail params={params} />
    </Suspense>
  );
}

async function NoticeDetail({ params }: { params: Params }) {
  const { id } = await params;
  // 실제 API: 주택목록(엑셀) 화면은 아직 목업만 있어서 일반 상세로 보여줘요
  if (!USE_MOCKS) {
    return <Responsive web={<WebDetail id={id} />} mobile={<MDetail id={id} />} />;
  }
  // 목업 단계: 없는 id는 첫 공고를 보여줘요
  const notice = notices.find((n) => n.id === id) ?? notices[0];

  // 주택목록(엑셀)이 붙은 공고는 목록·지도 중심 화면으로 보여줘요
  if (notice.kind === "units") {
    return (
      <Responsive
        web={<WebDetailUnits id={notice.id} />}
        mobile={<MDetailUnits id={notice.id} />}
      />
    );
  }
  return <Responsive web={<WebDetail id={notice.id} />} mobile={<MDetail id={notice.id} />} />;
}
