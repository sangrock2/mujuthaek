import type { Metadata } from "next";
import { MNotFoundState, WebNotFoundState } from "@/components/states/NotFoundState";
import { StateFrame } from "@/components/states/StateFrame";

export const metadata: Metadata = { title: "찾는 페이지가 없어요 | 무주택자들" };

export default function NotFound() {
  return <StateFrame web={<WebNotFoundState />} mobile={<MNotFoundState />} />;
}
