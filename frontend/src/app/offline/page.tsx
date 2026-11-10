import type { Metadata } from "next";
import { MLoadErrorState, WebLoadErrorState } from "@/components/states/LoadErrorState";
import { StateFrame } from "@/components/states/StateFrame";

export const metadata: Metadata = { title: "오프라인 | 무주택자들" };

/** 서비스 워커가 연결이 없을 때 보여주는 화면. 위에 오프라인 알림이 함께 떠요 */
export default function OfflinePage() {
  return <StateFrame web={<WebLoadErrorState />} mobile={<MLoadErrorState />} />;
}
