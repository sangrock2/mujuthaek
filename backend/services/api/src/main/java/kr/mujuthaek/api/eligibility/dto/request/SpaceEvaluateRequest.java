package kr.mujuthaek.api.eligibility.dto.request;

import jakarta.validation.Valid;

/**
 * 사업공간·사업 지원 하나의 판정 요청 (POST /spaces/{id}/evaluate, /supports/{id}/evaluate). 비우면 필요한
 * 입력(missingInputs)을 알려줘요. 공고마다 묻는 예/아니요 답(answers)은 받지 않아요: 자주 나오는 자격은 조건 입력으로 받고, 드문 조건은 원문 확인이에요
 * (2026-10-29 결정). 예전 화면이 answers를 보내도 쓰지 않아요.
 */
public record SpaceEvaluateRequest(@Valid JudgmentApplicantRequest applicant) {}
