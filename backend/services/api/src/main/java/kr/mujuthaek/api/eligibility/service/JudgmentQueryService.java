package kr.mujuthaek.api.eligibility.service;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Map;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.mapper.ApplicantMapper;
import kr.mujuthaek.api.eligibility.mapper.FrameReader;
import kr.mujuthaek.api.eligibility.mapper.FrameSpec;
import kr.mujuthaek.api.eligibility.mapper.JudgmentMapper;
import kr.mujuthaek.api.eligibility.model.JudgmentResult;
import kr.mujuthaek.api.eligibility.rule.BaseValues;
import kr.mujuthaek.api.eligibility.rule.SubscriptionDeposits;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant;
import kr.mujuthaek.api.eligibility.rule.frame.Frame;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudge;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudgment;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;

/**
 * 판정 틀 하나 판정 (4-05 주거, 4-06 창업지원, 4-07 사업공간). 틀 읽기 → 입력 검사 → 판정 → 정제된 결과까지 여기서 끝내요. 계산만 하고 입력·결과를
 * 저장하거나 로그에 남기지 않아요.
 *
 * <p>틀을 직접 받아요. 공고 ID로 틀을 가져오는 판정은 목록 판정({@link MatchQueryService})이 이 서비스의 판정을 써요.
 */
@Service
@Transactional(readOnly = true)
public class JudgmentQueryService {

  /** 틀에 기준일이 없을 때 쓰는 "판정하는 날"의 시간대. */
  private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

  private final FrameJudge judge;

  JudgmentQueryService(BaseValues baseValues, SubscriptionDeposits deposits) {
    this.judge = new FrameJudge(baseValues, deposits);
  }

  /**
   * 주거 자격 판정. 틀: housing-judgment.v1.
   *
   * @param applicant 사용자 입력. 비우면 이 공고에 필요한 입력(missingInputs)을 알려줘요
   */
  public JudgmentResult judgeHousing(JsonNode frame, JudgmentApplicantRequest applicant) {
    return judge(FrameSpec.HOUSING, frame, applicant);
  }

  /** 사업공간 입점 자격 판정. 틀: business-space-judgment.v1. */
  public JudgmentResult judgeBusinessSpace(JsonNode frame, JudgmentApplicantRequest applicant) {
    return judge(FrameSpec.BUSINESS_SPACE, frame, applicant);
  }

  /** 창업지원 사업 판정. 틀: startup-support-judgment.v1. */
  public JudgmentResult judgeStartupSupport(JsonNode frame, JudgmentApplicantRequest applicant) {
    return judge(FrameSpec.STARTUP_SUPPORT, frame, applicant);
  }

  /** 공고마다 묻는 예/아니요 답은 받지 않아요 (2026-10-29 결정). 질문 조건은 늘 원문 확인이에요. */
  private JudgmentResult judge(FrameSpec spec, JsonNode frame, JudgmentApplicantRequest applicant) {
    if (frame == null || frame.isNull()) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "frame: 판정 틀이 있어야 해요");
    }
    Frame read = FrameReader.read(frame, spec);
    Applicant input = ApplicantMapper.toApplicant(applicant, Map.of());
    return JudgmentMapper.toResult(judge(read, input));
  }

  /** 읽은 틀 하나를 판정해요. 틀에 기준일이 없으면(창업지원) 오늘(한국 시간) 기준이에요. */
  FrameJudgment judge(Frame frame, Applicant applicant) {
    return judge.judge(frame, applicant, LocalDate.now(KOREA));
  }
}
