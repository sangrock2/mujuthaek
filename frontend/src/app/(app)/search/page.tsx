import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MSearch } from "@/features/search/screens/MSearch";
import { WebSearch } from "@/features/search/screens/WebSearch";

export const metadata: Metadata = { title: "검색 | 무주택자들" };

export default function SearchPage() {
  return <Responsive web={<WebSearch />} mobile={<MSearch />} />;
}
