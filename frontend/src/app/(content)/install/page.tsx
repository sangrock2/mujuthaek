import type { Metadata } from "next";
import { MInstall } from "@/screens/install/MInstall";

export const metadata: Metadata = { title: "홈 화면에 추가 | 무주택자들" };

/** 모바일 전용 화면. PC에서는 390px 가운데 칸에 같은 화면을 보여줘요 */
export default function InstallPage() {
  return (
    <div className="bg-bg flex min-h-screen w-full flex-1 justify-center">
      <div className="flex w-full flex-col lg:max-w-[390px]">
        <MInstall />
      </div>
    </div>
  );
}
