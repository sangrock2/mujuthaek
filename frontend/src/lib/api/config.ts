/**
 * 목업으로 볼지, 실제 API를 부를지. 기본은 목업이에요.
 * 로컬 백엔드에 붙일 때는 .env.local에 NEXT_PUBLIC_USE_MOCKS=false
 */
export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS !== "false";
