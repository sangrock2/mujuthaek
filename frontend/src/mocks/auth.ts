// 화면용 예시 데이터 (디자인 WebWelcome 및 모바일). 실제 값은 API(GET /api/users/me)에서 받아요.

export type AuthSession = {
  /** 가입한 사람 이름 */
  userName: string;
};

export const authSession: AuthSession = {
  userName: "준",
};
