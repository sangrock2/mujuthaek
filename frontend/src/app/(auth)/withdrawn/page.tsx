import type { Metadata } from "next";
import { StateFrame } from "@/shared/states/StateFrame";
import { MWithdrawnState, WebWithdrawnState } from "@/shared/states/WithdrawnState";

export const metadata: Metadata = { title: "탈퇴했어요 | 무주택자들" };

export default function WithdrawnPage() {
  return <StateFrame web={<WebWithdrawnState />} mobile={<MWithdrawnState />} />;
}
