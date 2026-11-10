/** 커서 방식 목록 응답 (백엔드 CursorPageResponse) */
export type CursorPage<T> = { items: T[]; nextCursor: string | null; hasNext: boolean };
