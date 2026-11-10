package kr.mujuthaek.api.eligibility.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

/** 판정 요청 본문 { "applicant": { … } }. 판정 입력은 저장하지 않아요. */
public record EvaluateRequest(@Valid @NotNull ApplicantRequest applicant) {}
