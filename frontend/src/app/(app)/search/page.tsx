import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MSearch } from "@/screens/search/MSearch";
import { WebSearch } from "@/screens/search/WebSearch";

export const metadata: Metadata = { title: "검색 | 무주택자들" };

export default function SearchPage() {
  return <Responsive web={<WebSearch />} mobile={<MSearch />} />;
}
