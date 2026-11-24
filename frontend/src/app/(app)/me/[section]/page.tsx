import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { Responsive } from "@/shared/layout/Responsive";
import { MMeSection } from "@/features/me/screens/MMeSection";
import { WebMe } from "@/features/me/screens/WebMe";

import { meTabs, type MeTab } from "@/features/me/tabs";

export const metadata: Metadata = { title: "내 정보 | 무주택자들" };

export function generateStaticParams() {
  return meTabs.map((section) => ({ section }));
}

type Params = Promise<{ section: string }>;

/** 내 정보 세부 화면: 모바일은 따로 그리고, 웹은 내 정보의 그 탭으로 열어요 */
export default function MeSectionPage({ params }: { params: Params }) {
  return (
    <Suspense fallback={null}>
      <Section params={params} />
    </Suspense>
  );
}

async function Section({ params }: { params: Params }) {
  const { section } = await params;
  if (!meTabs.includes(section as MeTab)) notFound();
  const s = section as MeTab;
  return <Responsive web={<WebMe initialTab={s} />} mobile={<MMeSection section={s} />} />;
}
