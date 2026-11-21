package kr.mujuthaek.api.eligibility.service;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import kr.mujuthaek.api.benefit.domain.ApplyStatus;
import kr.mujuthaek.api.benefit.service.BenefitForJudgment;
import kr.mujuthaek.api.eligibility.dto.response.BenefitSearchResponse;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.Overall;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.springframework.stereotype.Service;

@Service
public class NoticeBenefitService {

  private static final Set<String> RECRUITING = Set.of("UPCOMING", "APPLYING", "ALWAYS");
  private static final Set<String> SALE = Set.of("PUBLIC_SALE", "PRIVATE_SALE");
  private static final Set<String> RENTAL_SUPPORT = Set.of("RENT", "MOVE_IN_GRANT");
  private static final Pattern PUBLIC_RENTAL_EXCLUDED =
      Pattern.compile("공공\\s*임대(?:주택)?(?:\\([^()]*\\))?\\s*(?:입주|거주|임차)[^.]{0,40}(?:제외|불가)");
  private static final Pattern PRIVATE_RENTAL_ONLY =
      Pattern.compile("민간\\s*(?:월세|임대주택|전세)\\s*(?:가구|거주|임차)");

  private final NoticeQueryService notices;
  private final BenefitEvaluationService evaluations;

  public NoticeBenefitService(NoticeQueryService notices, BenefitEvaluationService evaluations) {
    this.notices = notices;
    this.evaluations = evaluations;
  }

  /** 입주 지역으로 후보를 찾고 거주 자격은 신청자가 입력한 현재 주소로 판정해요. */
  public List<BenefitSearchResponse.Item> forNotice(UUID id, Applicant applicant) {
    var notice = notices.detail(id);
    var header = notice.header();
    String type = header.noticeType();
    if (!"HOUSING".equals(header.field())
        || !RECRUITING.contains(header.status())
        || (type != null && SALE.contains(type))) {
      return List.of();
    }

    List<String> regions =
        Stream.concat(
                Stream.of(header.regionCode()),
                notice.sites().stream().map(NoticeDetailResponse.Site::regionCode))
            .filter(code -> code != null && code.matches("[0-9]{5}([0-9]{5})?"))
            .map(code -> code.substring(0, 5))
            .distinct()
            .toList();
    boolean privateRental = "PUBLIC_SUPPORT_PRIVATE_RENTAL".equals(type);
    return evaluations.judgeAll(regions, applicant).stream()
        .filter(j -> relatedToHousing(j.benefit(), regions.isEmpty(), privateRental))
        .map(evaluations::item)
        .filter(i -> i.overall() != Overall.INELIGIBLE)
        .filter(i -> !ApplyStatus.UNKNOWN.name().equals(i.applyStatus()))
        .sorted(BenefitSearchService.order("RECOMMENDED"))
        .limit(12)
        .toList();
  }

  private static boolean relatedToHousing(
      BenefitForJudgment benefit, boolean nationwideOnly, boolean privateRental) {
    if (nationwideOnly && !"NATIONWIDE".equals(benefit.regionScope())) return false;
    if (!privateRental
        && benefit.conditions().stream()
            .map(BenefitForJudgment.Condition::rawText)
            .filter(java.util.Objects::nonNull)
            .anyMatch(
                text ->
                    PUBLIC_RENTAL_EXCLUDED.matcher(text).find()
                        || PRIVATE_RENTAL_ONLY.matcher(text).find())) {
      return false;
    }
    return benefit.supports().stream().anyMatch(s -> RENTAL_SUPPORT.contains(s.kind()));
  }
}
