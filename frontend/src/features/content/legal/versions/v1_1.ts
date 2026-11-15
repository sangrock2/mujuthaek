import { privacyPolicy as previous } from "./v1";
import type { LegalDocument } from "../types";

const update = (text: string) =>
  text
    .replaceAll("https://mujuthaek.vercel.app", "https://mujuthaek.store")
    .replaceAll("towo2ssss@gmail.com", "contact@mujuthaek.store")
    .replace(
      "현재 외부 이메일·웹 푸시 발송은 활성화되어 있지 않으며, 활성화 시 발송 수단과 변경 사항을 안내합니다.",
      "이메일 알림은 주소 인증과 별도 수신 동의 후 AWS SES로 발송합니다. 웹 푸시는 브라우저에서 별도로 허용한 경우에만 사용합니다.",
    );

/** v1.0 전문은 보존하고 선택 이메일 알림의 처리 사실을 추가해요. */
export const privacyPolicy: LegalDocument = {
  ...previous,
  version: "1.1",
  effectiveDate: "2026-11-15",
  summary: [
    ...previous.summary.map(update),
    "이메일 알림은 직접 등록한 주소를 인증하고 수신에 동의한 이용자에게만 발송하며, 언제든 수신을 해제할 수 있습니다.",
  ],
  sections: [
    ...previous.sections.map((section) => ({
      ...section,
      paragraphs: section.paragraphs?.map(update),
      items: section.items?.map(update),
      table: section.table && {
        ...section.table,
        rows: section.table.rows.map((row) => row.map(update)),
      },
    })),
    {
      id: "email-notifications",
      title: "선택 이메일 알림의 등록·인증·철회",
      paragraphs: [
        "계정 연락용 이메일과 알림 이메일은 서로 다른 목적으로 별도로 등록합니다. 기존 연락용 이메일 동의를 공고 알림 수신 동의로 사용하지 않습니다.",
        "알림 이메일 수집·이용에 동의한 이용자가 입력한 주소로 인증 메일을 보냅니다. 인증 링크는 15분 동안 한 번만 사용할 수 있습니다. 인증 후 선택한 알림 수신에 별도로 동의해야 맞춤 신규 공고·지원 소식, 신청 준비함·관심 공고 마감, 문의·제보 답변 알림을 발송합니다. 상품 광고나 제3자 광고를 보내기 위한 동의로 사용하지 않습니다.",
        "이메일 주소, 인증 요청·완료 시각, 토큰의 해시와 유효기간, 동의 문구 버전·시각, 선택한 알림 종류와 수신 해제 기록을 처리합니다. 인증 전 주소는 마지막 요청에서 24시간이 경과한 후 정기 작업으로 삭제합니다. 인증된 주소는 회원 탈퇴 또는 알림 이메일 삭제 시 삭제합니다. 백업에 남은 사본은 기존 백업 보관 정책에 따라 만료됩니다.",
        "인증 메일 남용을 막기 위해 회원별 요청 시각과 일별 횟수는 주소를 삭제한 뒤에도 유지할 수 있습니다. 이 기록에는 삭제한 이메일 주소나 인증 토큰 원문을 남기지 않습니다.",
        "AWS SES 서울 리전에서 발신·수신 주소와 메일 내용을 처리합니다. 발송 상태·반송·스팸 신고는 전달 결과 확인과 재발송 방지에 사용합니다. 일반 공고 알림 본문에는 문의 답변 원문이나 민감한 개인 정보를 포함하지 않습니다.",
        "알림 설정에서 수신 종류를 변경하거나 전체 수신을 끄고, 알림 이메일을 삭제할 수 있습니다. 메일의 수신 해제 링크로 로그인 없이 전체 이메일 알림을 끌 수도 있습니다. 수신 동의가 철회되면 발송 대기 중인 알림도 발송 직전 확인을 거쳐 차단합니다. 동의하지 않아도 이메일 알림 외의 서비스를 이용할 수 있습니다.",
      ],
    },
  ],
};
