import Link from "next/link";
import { routes } from "@/shared/lib/routes";

export function LegalPending({ title }: { title: string }) {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto flex w-full max-w-[800px] flex-1 flex-col gap-[20px] px-[24px] py-[64px]"
    >
      <h1 className="m-0 text-[28px] font-extrabold">{title}</h1>
      <p className="text-text-sub m-0 leading-[1.8]">
        정식 서비스 제공에 앞서 내용을 준비하고 있어요. 운영 정보와 개인정보 처리 내용을 확정한 뒤
        게시할 예정이에요.
      </p>
      <Link href={routes.main}>홈으로 돌아가기</Link>
    </main>
  );
}
