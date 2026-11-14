export * from "./types";
// 공개한 전문은 버전별로 보존하고 다음 개정에서 덮어쓰지 않아요.
export { serviceTerms } from "./versions/v1";
export { privacyPolicy } from "./versions/v1_1";
