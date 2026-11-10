package kr.mujuthaek.api.eligibility.service;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Comparator;
import java.util.List;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.mapper.LoanMapper;
import kr.mujuthaek.api.eligibility.model.LoanResult;
import kr.mujuthaek.api.eligibility.rule.loan.Borrower;
import kr.mujuthaek.api.eligibility.rule.loan.LoanCatalog;
import kr.mujuthaek.api.eligibility.rule.loan.LoanCheck;
import kr.mujuthaek.api.eligibility.rule.loan.LoanJudgment;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 대출 자격 판정: 기준일에 쓰는 대출 상품마다 이 사용자가 받을 수 있는지(가능 / 확인 필요 / 불가)와 이유를 봐요. 공고와 상관없이 사람 조건만 봐요. 입력 검사 →
 * 판정 → 정렬 → 정제된 결과까지 여기서 끝내요. 입력과 결과는 저장하거나 로그에 남기지 않아요.
 */
@Service
@Transactional(readOnly = true)
public class LoanQueryService {

  private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

  /** 지원 가능 → 확인 필요 → 불가 순, 같은 상태끼리는 상품 화면 순서(전세 → 월세 → 구입). */
  private static final Comparator<LoanJudgment> ORDER =
      Comparator.comparing(LoanJudgment::status)
          .thenComparingInt(j -> j.terms().displayOrder())
          .thenComparing(j -> j.terms().productCode());

  private final LoanCatalog catalog;

  LoanQueryService(LoanCatalog catalog) {
    this.catalog = catalog;
  }

  /**
   * @param applicant 사용자 입력 (판정과 같은 모양 + loan 칸). 비우면 모든 상품이 확인 필요 또는 불가가 돼요
   * @param asOf 기준일 (대출접수일로 봐요). 비우면 오늘(한국 시간)
   */
  public LoanResult judge(JudgmentApplicantRequest applicant, LocalDate asOf) {
    LocalDate day = asOf == null ? LocalDate.now(KOREA) : asOf;
    Borrower borrower = LoanMapper.toBorrower(applicant);
    List<LoanJudgment> judgments =
        catalog.asOf(day).stream()
            .map(terms -> LoanCheck.check(terms, borrower, day))
            .sorted(ORDER)
            .toList();
    return LoanMapper.toResult(day, judgments);
  }
}
