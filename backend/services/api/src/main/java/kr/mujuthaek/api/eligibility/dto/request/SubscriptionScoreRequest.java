package kr.mujuthaek.api.eligibility.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

/**
 * 청약 가점 계산 요청. 판정 입력(구간 값)이 아니라 가점용 정확한 값(birthDate·marital·marriedOn·homelessSince·homeOwner·
 * dependents·subscription.joinedOn)을 받아요.
 *
 * @param referenceDate 기준일 (모집공고일). 비우면 오늘
 */
public record SubscriptionScoreRequest(
    @Valid @NotNull ScoreApplicantRequest applicant, LocalDate referenceDate) {}
