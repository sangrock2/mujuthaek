package kr.mujuthaek.api.user.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;

/**
 * 가입 필수 동의.
 *
 * @param termsVersion 화면이 보여 준 이용약관 버전 (예: 1.0)
 * @param privacyVersion 화면이 보여 준 개인정보 수집·이용 동의(처리방침) 버전 (예: 1.0)
 * @param ageOver14 만 14세 이상이라는 확인. true여야 해요 (나이·생년월일은 받지 않아요)
 */
public record TermsAgreementRequest(
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED, example = "1.0", maxLength = 20)
        String termsVersion,
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED, example = "1.0", maxLength = 20)
        String privacyVersion,
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED, example = "true") Boolean ageOver14) {}
