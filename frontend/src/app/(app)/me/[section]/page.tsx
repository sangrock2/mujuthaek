import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { Responsive } from "@/components/layout/Responsive";
import { MMeSection, type MeSection } from "@/screens/me/MMeSection";
import { WebMe } from "@/screens/me/WebMe";

export const metadata: Metadata = { title: "내 정보 | 무주택자들" };

const sections: MeSection[] = ["favorites", "interests", "notifications", "reports"];

export function generateStaticParams() {
  return sections.map((section) => ({ section }));
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
  if (!sections.includes(section as MeSection)) notFound();
  const s = section as MeSection;
  return <Responsive web={<WebMe initialTab={s} />} mobile={<MMeSection section={s} />} />;
}
