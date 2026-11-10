package kr.mujuthaek.api.eligibility.rule.loan;

import java.time.LocalDate;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import java.util.function.Function;
import java.util.stream.Collectors;

/** 대출 상품 조건 조회. 판정 코드는 이 인터페이스만 알고, 값은 service가 DB에서 읽어 줘요. */
public interface LoanCatalog {

  /** 기준일에 쓰는 조건: 상품마다 시행일이 기준일 이전인 행 중 가장 늦은 것. 화면 순서(displayOrder)대로예요. */
  List<LoanTerms> asOf(LocalDate day);

  /** 여러 시점의 행에서 기준일에 쓰는 행만 골라요. 시행일 전인 상품은 빠져요. */
  static List<LoanTerms> latest(Collection<LoanTerms> rows, LocalDate day) {
    return rows.stream()
        .filter(t -> !t.effectiveFrom().isAfter(day))
        .collect(
            Collectors.toMap(
                LoanTerms::productCode,
                Function.identity(),
                (a, b) -> a.effectiveFrom().isAfter(b.effectiveFrom()) ? a : b))
        .values()
        .stream()
        .sorted(
            Comparator.comparingInt(LoanTerms::displayOrder).thenComparing(LoanTerms::productCode))
        .toList();
  }
}
