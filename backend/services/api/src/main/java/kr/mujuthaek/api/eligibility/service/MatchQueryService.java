package kr.mujuthaek.api.eligibility.service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.mapper.ApplicantMapper;
import kr.mujuthaek.api.eligibility.mapper.FrameReader;
import kr.mujuthaek.api.eligibility.mapper.FrameSpec;
import kr.mujuthaek.api.eligibility.mapper.MatchMapper;
import kr.mujuthaek.api.eligibility.model.JudgmentResult;
import kr.mujuthaek.api.eligibility.model.MatchResult;
import kr.mujuthaek.api.eligibility.model.NoticeCandidate;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant;
import kr.mujuthaek.api.eligibility.rule.frame.Frame;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudgment;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 목록 판정 (4-05 주거, 4-06 창업지원, 4-07 사업공간). 사용자 입력 하나로 열린 공고(창업지원은 지원사업)를 모두 판정하고, 지원 가능·확인 필요만 남겨 정렬한
 * 결과까지 여기서 끝내요.
 *
 * <p>순서: 지원 가능 → 확인 필요, 그 안에서 내 순위(1순위 → 2순위 → … → 순위 없음), 그다음 마감 빠른 순이에요.
 *
 * <p>지역으로는 거르지 않아요. 공고마다 regionCodes를 실어 보내면 프론트가 걸러요. 입력과 결과는 저장하거나 로그에 남기지 않아요.
 */
@Service
@Transactional(readOnly = true)
public class MatchQueryService {

  private static final Logger log = LoggerFactory.getLogger(MatchQueryService.class);

  private static final Comparator<MatchResult.Item> ORDER =
      Comparator.comparing(MatchResult.Item::status)
          .thenComparing(MatchResult.Item::rank, Comparator.nullsLast(Comparator.naturalOrder()))
          .thenComparing(
              MatchResult.Item::applyEnd, Comparator.nullsLast(Comparator.naturalOrder()))
          .thenComparing(MatchResult.Item::noticeId);

  private final JudgmentCandidates candidates;
  private final JudgmentQueryService judgments;

  MatchQueryService(JudgmentCandidates candidates, JudgmentQueryService judgments) {
    this.candidates = candidates;
    this.judgments = judgments;
  }

  /**
   * 주거 목록 판정.
   *
   * @param applicant 사용자 입력 (상세 판정과 같은 모양). 비우면 모든 공고가 확인 필요가 돼요. 질문(ASK) 답은 받지 않아요. 답이 필요한 공고는 확인
   *     필요로 두고 상세에서 물어요
   */
  public MatchResult matchHousing(JudgmentApplicantRequest applicant) {
    return match(FrameSpec.HOUSING, applicant);
  }

  /** 사업공간 목록 판정. 결과 모양은 주거와 같아요. */
  public MatchResult matchBusinessSpace(JudgmentApplicantRequest applicant) {
    return match(FrameSpec.BUSINESS_SPACE, applicant);
  }

  /** 창업지원 목록 판정. 결과 모양은 주거와 같아요 (noticeId는 지원사업 ID, 수집 DB 정책 ID). */
  public MatchResult matchStartupSupport(JudgmentApplicantRequest applicant) {
    return match(FrameSpec.STARTUP_SUPPORT, applicant);
  }

  /** 사업공간 맞춤 목록(POST /spaces/search)용: 지원 불가까지 열린 사업공간 공고·모집 정책을 모두 판정해요. 정렬·걸러내기는 부르는 쪽이 해요. */
  public List<MatchResult.Item> judgeBusinessSpaceAll(JudgmentApplicantRequest applicant) {
    return judgeAll(FrameSpec.BUSINESS_SPACE, applicant, true);
  }

  /** 사업 지원 맞춤 목록(POST /supports/search)용: 지원 불가까지 열린 창업지원 사업을 모두 판정해요. */
  public List<MatchResult.Item> judgeStartupSupportAll(JudgmentApplicantRequest applicant) {
    return judgeAll(FrameSpec.STARTUP_SUPPORT, applicant, true);
  }

  /**
   * 사업공간 하나의 판정 (POST /spaces/{id}/evaluate). 열린 공고·모집 정책에서 찾아요.
   *
   * @return 열린 사업공간이 아니면 empty. 판정 틀이 아직 없으면 judgment가 null
   */
  public Optional<OneJudgment> judgeBusinessSpace(UUID id, JudgmentApplicantRequest applicant) {
    return judgeOne(FrameSpec.BUSINESS_SPACE, id, applicant);
  }

  /**
   * 창업지원 사업 하나의 판정 (POST /supports/{id}/evaluate). 열린 지원사업에서 찾아요.
   *
   * @return 열린 지원사업이 아니면 empty
   */
  public Optional<OneJudgment> judgeStartupSupport(UUID id, JudgmentApplicantRequest applicant) {
    return judgeOne(FrameSpec.STARTUP_SUPPORT, id, applicant);
  }

  /**
   * 공간·지원사업 하나의 판정 결과.
   *
   * @param judgment 판정 틀이 아직 없으면 null (화면은 "자격 조건 정리 중")
   */
  public record OneJudgment(NoticeCandidate notice, JudgmentResult judgment) {}

  private Optional<OneJudgment> judgeOne(
      FrameSpec spec, UUID id, JudgmentApplicantRequest applicant) {
    return candidates.openNotices(spec.field()).stream()
        .filter(n -> n.noticeId().equals(id))
        .findFirst()
        .map(
            n ->
                readFrame(n, spec) == null
                    ? new OneJudgment(n, null)
                    : new OneJudgment(
                        n,
                        spec == FrameSpec.STARTUP_SUPPORT
                            ? judgments.judgeStartupSupport(n.frame(), applicant)
                            : judgments.judgeBusinessSpace(n.frame(), applicant)));
  }

  private MatchResult match(FrameSpec spec, JudgmentApplicantRequest request) {
    List<MatchResult.Item> items = new ArrayList<>(judgeAll(spec, request, false));
    items.sort(ORDER);
    return MatchMapper.toResult(spec.field(), items);
  }

  private List<MatchResult.Item> judgeAll(
      FrameSpec spec, JudgmentApplicantRequest request, boolean includeIneligible) {
    Applicant applicant = ApplicantMapper.toApplicant(request, Map.of());
    List<MatchResult.Item> items = new ArrayList<>();
    for (NoticeCandidate notice : candidates.openNotices(spec.field())) {
      Frame frame = readFrame(notice, spec);
      if (frame == null) {
        items.add(MatchMapper.notReady(notice));
        continue;
      }
      FrameJudgment judgment = judgments.judge(frame, applicant);
      if (includeIneligible || judgment.result() != Eligibility.INELIGIBLE) {
        items.add(MatchMapper.judged(notice, judgment));
      }
    }
    return items;
  }

  /** 판정 틀이 없거나 형식이 틀리면 null. 사용자는 이 공고를 "자격 조건 정리 중"으로 보고, 틀 문제는 로그로 알려요 (사용자 입력은 넣지 않아요). */
  private static Frame readFrame(NoticeCandidate notice, FrameSpec spec) {
    if (notice.frame() == null) {
      return null;
    }
    try {
      return FrameReader.read(notice.frame(), spec);
    } catch (CustomException e) {
      log.warn(
          "공고 {} v{}의 판정 틀을 읽지 못해 확인 필요로 둬요: {}",
          notice.noticeId(),
          notice.version(),
          e.getMessage());
      return null;
    }
  }
}
