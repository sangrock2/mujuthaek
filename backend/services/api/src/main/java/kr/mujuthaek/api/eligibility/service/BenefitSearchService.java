package kr.mujuthaek.api.eligibility.service;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.common.pagination.CursorQuery;
import kr.mujuthaek.api.common.text.Keywords;
import kr.mujuthaek.api.eligibility.dto.request.BenefitSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.BenefitSearchResponse;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.Overall;
import org.springframework.stereotype.Service;

/** 혜택 맞춤 목록: 찾아볼 지역의 열린 혜택을 모두 판정하고, 지원 불가를 빼고 정렬해요. 판정은 계산값이라 목록 안 위치를 커서로 써요. 판정 입력은 저장하지 않아요. */
@Service
public class BenefitSearchService {

  static final List<String> CATEGORIES = List.of("HOUSING", "ASSET", "TRANSPORT");

  private final BenefitEvaluationService evaluations;

  public BenefitSearchService(BenefitEvaluationService evaluations) {
    this.evaluations = evaluations;
  }

  public BenefitSearchResponse search(BenefitSearchRequest request) {
    String sort = request.sortOrDefault();
    CursorQuery page = CursorQuery.of(request.cursor(), request.size(), sort);
    Applicant applicant =
        request.applicant() == null ? Applicant.empty() : request.applicant().toApplicant();
    Keywords keywords = request.keywords();
    List<BenefitSearchResponse.Item> judged =
        evaluations.judgeAll(request.regionCodes(), applicant).stream()
            .map(evaluations::item)
            .filter(i -> keywords.matches(i.title(), i.agency()))
            .toList();
    List<BenefitSearchResponse.Item> open =
        judged.stream().filter(i -> i.overall() != Overall.INELIGIBLE).toList();
    var summary =
        new BenefitSearchResponse.Summary(
            count(judged, Overall.ELIGIBLE),
            count(judged, Overall.NEEDS_INPUT),
            count(judged, Overall.INELIGIBLE),
            judged.stream()
                .filter(i -> i.overall() == Overall.ELIGIBLE)
                .mapToLong(BenefitSearchResponse.Item::annualAmountWon)
                .sum());
    Map<String, Integer> categoryCounts = new LinkedHashMap<>();
    for (String c : CATEGORIES) {
      categoryCounts.put(c, (int) open.stream().filter(i -> c.equals(i.category())).count());
    }
    List<String> categories = request.categories();
    List<BenefitSearchResponse.Item> shown =
        open.stream()
            .filter(i -> categories.isEmpty() || categories.contains(i.category()))
            .sorted(order(sort))
            .toList();
    int from = page.after() == null ? 0 : page.after().position() + 1;
    List<Integer> positions =
        java.util.stream.IntStream.range(Math.min(from, shown.size()), shown.size())
            .limit(page.fetchSize())
            .boxed()
            .toList();
    var pageOf =
        CursorPageResponse.from(
            positions, page.size(), shown::get, i -> CursorKey.of(sort, i, shown.get(i).id()));
    return new BenefitSearchResponse(
        summary, categoryCounts, pageOf.items(), pageOf.nextCursor(), pageOf.hasNext());
  }

  private static Comparator<BenefitSearchResponse.Item> order(String sort) {
    Comparator<BenefitSearchResponse.Item> deadline =
        Comparator.comparing(
            BenefitSearchResponse.Item::dday, Comparator.nullsLast(Comparator.naturalOrder()));
    Comparator<BenefitSearchResponse.Item> amount =
        Comparator.comparingLong(BenefitSearchResponse.Item::annualAmountWon).reversed();
    Comparator<BenefitSearchResponse.Item> base =
        switch (sort) {
          case "DEADLINE" -> deadline;
          case "AMOUNT" -> amount.thenComparing(deadline);
          default ->
              Comparator.comparing((BenefitSearchResponse.Item i) -> i.overall().ordinal())
                  .thenComparing(amount)
                  .thenComparing(deadline);
        };
    return base.thenComparing(BenefitSearchResponse.Item::id);
  }

  private static int count(List<BenefitSearchResponse.Item> items, Overall overall) {
    return (int) items.stream().filter(i -> i.overall() == overall).count();
  }
}
