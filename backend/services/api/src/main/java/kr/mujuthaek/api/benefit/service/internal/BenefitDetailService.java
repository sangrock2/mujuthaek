package kr.mujuthaek.api.benefit.service.internal;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import kr.mujuthaek.api.benefit.domain.ApplyStatus;
import kr.mujuthaek.api.benefit.dto.response.BenefitDetailResponse;
import kr.mujuthaek.api.benefit.repository.BenefitRepository;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.springframework.stereotype.Service;

/** 혜택 상세 (공개 정보). */
@Service
public class BenefitDetailService {

  private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

  private final BenefitRepository benefits;
  private final Clock clock;

  public BenefitDetailService(BenefitRepository benefits, Clock clock) {
    this.benefits = benefits;
    this.clock = clock;
  }

  public BenefitDetailResponse detail(UUID id) {
    var r = benefits.find(id).orElseThrow(() -> new CustomException(ErrorCode.BENEFIT_NOT_FOUND));
    LocalDate today = LocalDate.now(clock.withZone(KOREA));
    ApplyStatus status = ApplyStatus.of(r.applyAlways(), r.applyStart(), r.applyEnd(), today);
    Integer dday =
        r.applyAlways() || r.applyEnd() == null
            ? null
            : (int) ChronoUnit.DAYS.between(today, r.applyEnd());
    return new BenefitDetailResponse(
        new BenefitDetailResponse.Header(
            r.id(),
            r.title(),
            r.agency(),
            r.category(),
            r.summary(),
            r.regionScope(),
            r.regionNames(),
            r.regionCodes(),
            status.name(),
            r.applyStart(),
            r.applyEnd(),
            dday,
            r.businessStart(),
            r.businessEnd(),
            r.scheduleText(),
            r.needsReview()),
        r.supports().stream()
            .map(
                s ->
                    new BenefitDetailResponse.Support(
                        s.kind(),
                        s.amountMax() == null ? null : s.amountMax() * BenefitQueryService.MANWON,
                        s.amountPer(),
                        s.months(),
                        s.ratePct(),
                        s.rawText(),
                        s.evidence()))
            .toList(),
        r.howToApply(),
        r.documents(),
        r.contact(),
        r.conditions().stream()
            .map(
                c ->
                    new BenefitDetailResponse.Condition(
                        c.type(), c.group(), c.known(), c.rawText(), c.evidence()))
            .toList(),
        java.util.List.of(
            new BenefitDetailResponse.Source(r.sourceCode(), r.detailUrl(), r.applyUrl())));
  }
}
