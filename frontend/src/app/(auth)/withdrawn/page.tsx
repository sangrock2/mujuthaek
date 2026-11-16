import type { Metadata } from "next";
import { StateFrame } from "@/shared/states/StateFrame";
import { MWithdrawnState, WebWithdrawnState } from "@/shared/states/WithdrawnState";

// 로그인 없이 열리는 주소라 제목도 결과를 단정하지 않아요. 결과 문구는 이 탭에서 시작한 탈퇴일 때만 보여요
export const metadata: Metadata = {
  title: "회원 탈퇴 | 무주택자들",
  robots: { index: false, follow: false },
};

export default function WithdrawnPage() {
  return <StateFrame web={<WebWithdrawnState />} mobile={<MWithdrawnState />} />;
}
