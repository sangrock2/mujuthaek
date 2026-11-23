import type { LegalDocument } from "../types";
import { privacyPolicy as previous } from "./v1_1";

const updateDelivery = (text: string) =>
  text.replace(
    "이메일 알림은 주소 인증과 별도 수신 동의 후 AWS SES로 발송합니다.",
    "이메일 알림은 등록 시 수신에 동의하고 주소를 인증한 이용자에게 AWS SES로 발송합니다.",
  );

export const privacyPolicy: LegalDocument = {
  ...previous,
  version: "1.2",
  effectiveDate: "2026-11-24",
  sections: previous.sections.map((section) =>
    section.id === "email-notifications"
      ? {
          ...section,
          paragraphs: section.paragraphs?.map((paragraph) =>
            paragraph
              .replace(
                "알림 이메일 수집·이용에 동의한 이용자가 입력한 주소로 인증 메일을 보냅니다. 인증 링크는 15분 동안 한 번만 사용할 수 있습니다. 인증 후 선택한 알림 수신에 별도로 동의해야",
                "이메일 수집·이용 및 알림 수신에 동의하고 인증번호를 요청하면 입력한 주소로 6자리 번호를 보냅니다. 인증번호는 5분 동안 한 번만 사용할 수 있습니다. 주소를 인증한 뒤",
              )
              .replace("토큰의 해시와 유효기간", "인증번호의 검증용 해시와 유효기간·확인 횟수"),
          ),
        }
      : {
          ...section,
          paragraphs: section.paragraphs?.map(updateDelivery),
          items: section.items?.map(updateDelivery),
          table: section.table && {
            ...section.table,
            rows: section.table.rows.map((row) => row.map(updateDelivery)),
          },
        },
  ),
};
