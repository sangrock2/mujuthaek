package kr.mujuthaek.api.eligibility.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;

/** 준비할 돈 계산 요청 { applicant, depositWon }. */
public record PrepareCostRequest(
    @Valid @NotNull ApplicantRequest applicant, @NotNull @PositiveOrZero Long depositWon) {}
