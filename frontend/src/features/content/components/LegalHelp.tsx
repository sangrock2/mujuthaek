import Link from "next/link";
import { LEGAL_CONTACT } from "@/features/content/legal/documents";

const linkClass = "text-brand-strong underline underline-offset-4";

export function LegalHelp({ privacy }: { privacy: boolean }) {
  const requestHref = `mailto:${LEGAL_CONTACT}?subject=${encodeURIComponent(privacy ? "[개인정보 권리 행사 요청]" : "[이용 제한 이의 신청·서비스 문의]")}`;
  return (
    <section
      aria-label={privacy ? "개인정보 권리 행사 안내" : "서비스 문의와 이의 신청 안내"}
      className="rounded-card border-line bg-surface mb-[24px] border border-solid p-[20px] text-[14px] leading-[1.9] sm:p-[28px]"
    >
      <h2 className="m-0 mb-[12px] text-[18px] font-bold">
        {privacy ? "내 정보를 관리하려면" : "문의하거나 이의를 신청하려면"}
      </h2>
      {privacy ? (
        <ol className="m-0 flex list-decimal flex-col gap-[12px] pl-[20px]">
          <li>
            <strong>이 기기에 저장한 조건 삭제</strong>
            <p className="m-0">
              <Link href="/me?tab=privacy" className={linkClass}>
                개인정보 설정 열기
              </Link>
              에서 ‘저장한 조건 모두 지우기’를 선택하세요. 모바일에서는 ‘내 정보’의 ‘저장한 조건
              지우기’를 이용하세요. 다른 기기·브라우저에 저장한 데이터는 각각 삭제해야 하며,
              브라우저 설정의 사이트 데이터 삭제도 사용할 수 있습니다.
            </p>
          </li>
          <li>
            <strong>연락용 이메일 삭제·동의 철회</strong>
            <p className="m-0">
              로그인 후 ‘내 정보’의 ‘연락용 이메일’에서 ‘이메일 지우기 (동의 철회)’를 선택하세요.
              연락용 이메일 삭제와 회원 탈퇴는 별도입니다.
            </p>
          </li>
          <li>
            <strong>회원 탈퇴</strong>
            <p className="m-0">
              로그인 후 ‘내 정보’에서 ‘회원 탈퇴’ → ‘확인하고 탈퇴하기’를 선택하고 연결된 소셜
              계정으로 재인증하세요. PC에서는 개인정보 설정에서, 모바일에서는 내 정보 하단에서
              시작할 수 있습니다. 기기에 저장한 조건과 소셜 제공자 계정은 별도로 확인해 주세요.
            </p>
          </li>
          <li>
            <strong>열람·정정·삭제·처리정지 요청</strong>
            <p className="m-0">
              <a href={requestHref} className={linkClass}>
                이메일로 권리 행사 요청하기
              </a>
              에서 요청 종류와 대상 정보를 알려주세요. 로그인할 수 없는 경우에도 접수할 수 있습니다.
              필요한 경우 본인·대리 권한 확인 방법을 회신하며, 비밀번호·인증
              코드·신분증·주민등록번호를 먼저 보내지 마세요.
            </p>
          </li>
        </ol>
      ) : (
        <>
          <p className="m-0 mb-[12px]">
            <a href={requestHref} className={linkClass}>
              서비스 문의·이용 제한 이의 신청하기
            </a>
            에서 문제가 생긴 기능, 발생 시점, 표시된 안내와 원하는 조치를 알려주세요. 계정 확인이
            필요하면 안전한 확인 방법을 회신합니다. 비밀번호·인증 코드와 전체 로그인 콜백 URL은
            보내지 마세요.
          </p>
          <p className="m-0">
            접수 내용과 관련 기록을 확인해 처리 결과 또는 추가 확인 사항을 회신합니다. 24시간 실시간
            상담을 제공하는 창구는 아닙니다.
          </p>
        </>
      )}
      <p className="text-text-sub mt-[16px] mb-0">
        이 안내는 현재 기능의 이용 방법입니다. 개인정보의 처리 범위·삭제 예외·백업 처리는 아래
        전문을 확인해 주세요. 이메일 앱이 열리지 않으면 {LEGAL_CONTACT}으로 직접 보내주세요.
      </p>
    </section>
  );
}
