package kr.mujuthaek.api.eligibility.dto.request;

import jakarta.validation.Valid;
import java.time.LocalDate;
import kr.mujuthaek.api.common.validation.ReasonableDate;

/**
 * 대출 자격 판정 요청 (POST /api/v1/eligibility/loans/evaluate). 공고는 받지 않아요. 저장하거나 로그에 남기지 않아요.
 *
 * @param profile 사용자 입력 (공고 판정과 같은 모양 + loan 칸). 비우면 모든 상품이 확인 필요 또는 불가가 돼요. 다른 판정과 같은 목록 길이 상한을
 *     검사해요
 * @param asOf 기준일 (대출접수일로 봐요). 비우면 오늘(한국 시간)
 */
public record LoanEvaluateRequest(
    @Valid JudgmentApplicantRequest profile, @ReasonableDate LocalDate asOf) {}
