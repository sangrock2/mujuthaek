package kr.mujuthaek.api.common.event;

import java.time.LocalDate;
import java.util.UUID;

/** 혜택·지원사업 신청이 마감됨. */
public record BenefitClosed(UUID benefitId, LocalDate closedOn) {}
