import type { Metadata } from "next";
import { MNotFoundState, WebNotFoundState } from "@/shared/states/NotFoundState";
import { StateFrame } from "@/shared/states/StateFrame";

export const metadata: Metadata = { title: "찾는 페이지가 없어요 | 무주택자들" };

export default function NotFound() {
  return <StateFrame web={<WebNotFoundState />} mobile={<MNotFoundState />} />;
}
