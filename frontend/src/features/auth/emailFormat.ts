// 연락용 이메일 형식 검사. 백엔드 ContactEmailService와 같은 규칙이에요 (바꾸면 둘 다)
// 아이디@도메인.최상위 · 공백(전각 공백 포함)·@ 두 개·제어 문자는 안 돼요 · 아이디 64자, 전체 254자까지
// <>()[]\,;:"도 안 돼요: 「이름<남@x.com>」 같은 표시 이름 형식으로 주소별 제한을 피할 수 있었어요(2026-11-16 보안 감사)

const EMAIL =
  /^[^\s\p{Z}@\p{Cc}<>()[\]\\,;:"]{1,64}@[^\s\p{Z}@.\p{Cc}<>()[\]\\,;:"]+(\.[^\s\p{Z}@.\p{Cc}<>()[\]\\,;:"]+)+$/u;

export const MAX_EMAIL_LENGTH = 254;

/** 앞뒤 공백을 뺀 값으로 봐요 (빈 값은 따로 봐요) */
export function isEmail(value: string) {
  const v = value.trim();
  return v.length <= MAX_EMAIL_LENGTH && EMAIL.test(v);
}
