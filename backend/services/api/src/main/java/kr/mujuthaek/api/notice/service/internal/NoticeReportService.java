package kr.mujuthaek.api.notice.service.internal;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.benefit.service.BenefitSummary;
import kr.mujuthaek.api.common.event.BenefitReportAnswered;
import kr.mujuthaek.api.common.event.GeneralReportAnswered;
import kr.mujuthaek.api.common.event.NoticeReportAnswered;
import kr.mujuthaek.api.common.event.ProgramReportAnswered;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.id.UuidV7;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.dto.request.AdminReportResolveRequest;
import kr.mujuthaek.api.notice.dto.request.GeneralReportRequest;
import kr.mujuthaek.api.notice.dto.request.NoticeReportRequest;
import kr.mujuthaek.api.notice.dto.response.AdminReportDetailResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReportListResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReportReviewResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeReportCreatedResponse;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository.Report;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;

/**
 * 공고 제보: 회원이 공고 값이 다르다고 알리고, 관리자가 처리해 답을 남겨요. 답장 발송은 {@link NoticeReportAnswered} 이벤트로 알림 쪽에 넘겨요.
 *
 * <p>제보 내용(칸 이름·값·설명)은 로그에 남기지 않아요.
 */
@Service
public class NoticeReportService {

  /** 회원 한 명이 하루(한국 시간)에 낼 수 있는 제보 수. */
  static final int DAILY_LIMIT = 20;

  static final List<String> STATUSES = List.of("NEW", "DOING", "DONE");

  /** 일반 제보 종류: 빠진 공고·정책, 틀린 정보, 화면 오류, 기타 */
  static final List<String> GENERAL_KINDS =
      List.of("MISSING_NOTICE", "WRONG_INFO", "APP_ERROR", "ETC");

  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
  private static final int LIST_LIMIT = 100;

  private final NoticeReportRepository reports;
  private final ExtractionReviewClient extraction;
  private final ApplicationEventPublisher events;
  private final Clock clock;
  private final BenefitQueryService benefits;

  public NoticeReportService(
      NoticeReportRepository reports,
      ExtractionReviewClient extraction,
      ApplicationEventPublisher events,
      Clock clock,
      BenefitQueryService benefits) {
    this.reports = reports;
    this.extraction = extraction;
    this.events = events;
    this.clock = clock;
    this.benefits = benefits;
  }

  /**
   * 「고치기」: 공고의 가장 새로 발행한 추출 결과를 검수 대기로 다시 열고 이 제보(와 같은 칸의 처리 전 제보)에 이어요. 관리자는 검수 화면에서 칸을 고쳐 승인(다시
   * 발행)한 뒤 {@link #resolve}로 제보를 끝내요.
   *
   * <p>추출 검수 API를 부르는 동안 DB 연결을 잡지 않도록 트랜잭션 없이 처리해요. 연결 갱신(linkReview)은 한 문장이라 그 자체로 원자적이에요
   * (2026-10-25 검토).
   */
  public AdminReportReviewResponse openReview(UUID id, String admin) {
    Report report = find(id);
    if ("DONE".equals(report.status())) {
      throw new CustomException(ErrorCode.CONFLICT, "이미 처리한 제보예요");
    }
    if (report.benefitPolicyId() != null) {
      return openBenefitReview(report, admin);
    }
    if (report.noticeId() == null && report.rawPolicyId() == null) {
      throw new CustomException(ErrorCode.CONFLICT, "일반 제보는 「고치기」가 없어요. 확인 뒤 처리 끝으로 답해 주세요");
    }
    if (report.noticeId() == null) {
      throw new CustomException(
          ErrorCode.CONFLICT, "창업지원 사업은 아직 「고치기」를 지원하지 않아요. 확인 뒤 처리 끝으로 답해 주세요");
    }
    UUID rawPost =
        reports
            .currentRawPost(report.noticeId())
            .orElseThrow(() -> new CustomException(ErrorCode.NOTICE_NOT_FOUND));
    JsonNode opened = extraction.reopen(rawPost.toString(), admin, "공고 제보: " + report.field());
    UUID reviewId = UUID.fromString(opened.path("jobId").asString());
    List<UUID> ids = new ArrayList<>(List.of(id));
    reports.sameGroup(report, id).stream()
        .filter(r -> !"DONE".equals(r.status()))
        .forEach(r -> ids.add(r.id()));
    reports.linkReview(ids, reviewId, admin, clock.instant());
    return new AdminReportReviewResponse(id, reviewId, opened.path("reopened").asBoolean(true));
  }

  /** 혜택 정책 「고치기」: 그 정책의 가장 새 정제 결과를 혜택 검수 대기로 다시 열어요(관리자 혜택 검수 화면에서 고쳐 승인). */
  private AdminReportReviewResponse openBenefitReview(Report report, String admin) {
    JsonNode opened =
        extraction.benefitReopen(
            report.benefitPolicyId().toString(), admin, "정책 제보: " + report.field());
    UUID reviewId = UUID.fromString(opened.path("reviewId").asString());
    List<UUID> ids = new ArrayList<>(List.of(report.id()));
    reports.sameGroup(report, report.id()).stream()
        .filter(r -> !"DONE".equals(r.status()))
        .forEach(r -> ids.add(r.id()));
    reports.linkReview(ids, reviewId, admin, clock.instant());
    return new AdminReportReviewResponse(
        report.id(), reviewId, opened.path("reopened").asBoolean(true));
  }

  /**
   * 회원의 주거·복지 정책(혜택) 제보. 추출 서비스에 정제 결과가 있는 정책에만 받고, 제목은 그때 받아 둬요(api에 혜택 표가 아직 없어요).
   *
   * @param targetId 정책 원본 ID (policy.extracted의 rawPolicyId) 또는 혜택 ID (혜택 화면이 쓰는 ID, 원본 ID로 바꿔요)
   *     <p>추출 서비스에서 제목을 받는 동안 DB 연결을 잡지 않도록 트랜잭션 없이 처리해요(넣기는 한 문장).
   */
  public NoticeReportCreatedResponse reportBenefit(
      UUID targetId, NoticeReportRequest request, String reporter) {
    UUID reporterId = reporterId(reporter);
    UUID policyId = benefits.findRawPolicyId(targetId).orElse(targetId);
    if (blank(request.reportedValue()) && blank(request.note())) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "맞는 값이나 설명 중 하나는 적어 주세요");
    }
    // 제목은 이 서버의 혜택에서 먼저 찾아요. 예전에는 늘 추출 서비스에 물어서, 그쪽에 결과가 없는 환경(운영 결과를 받아 쓰는 개발 서버)에서는
    // 혜택 제보가 모두 404였어요(2026-10-29 QA). 이 서버에 없을 때만 추출 서비스에 물어요
    String title = benefits.findSummaryByRawPolicyId(policyId).map(b -> b.title()).orElse(null);
    if (title == null) {
      title = extractionBenefitTitle(policyId);
    }
    Instant now = clock.instant();
    Instant todayStart = LocalDate.ofInstant(now, SEOUL).atStartOfDay(SEOUL).toInstant();
    if (reports.countSince(reporterId, todayStart) >= DAILY_LIMIT) {
      throw new CustomException(ErrorCode.RATE_LIMITED, "제보는 하루에 " + DAILY_LIMIT + "건까지 보낼 수 있어요");
    }
    UUID id = UuidV7.next();
    boolean added =
        reports.insert(
            new NoticeReportRepository.Row(
                id,
                null,
                null,
                policyId,
                title,
                reporterId,
                request.field().trim(),
                trim(request.currentValue()),
                trim(request.reportedValue()),
                trim(request.note()),
                trim(request.screen()),
                now));
    if (!added) {
      throw new CustomException(ErrorCode.CONFLICT, "같은 칸에 보낸 제보를 아직 확인하고 있어요");
    }
    return new NoticeReportCreatedResponse(id, "NEW");
  }

  /** 이 서버에 없는 정책의 제목을 추출 서비스에서 찾아요. 거기에도 없으면 404. */
  private String extractionBenefitTitle(UUID policyId) {
    try {
      return extraction.benefit(policyId.toString()).path("title").asString();
    } catch (CustomException e) {
      if (e.errorCode() == ErrorCode.NOTICE_REVIEW_NOT_FOUND) {
        throw new CustomException(ErrorCode.NOT_FOUND, "정책을 찾을 수 없어요");
      }
      if (e.errorCode() == ErrorCode.NOTICE_REVIEW_UNAVAILABLE) {
        // 회원에게 「검수 서버」라는 내부 사정 대신 제보를 지금 받을 수 없다고 알려요
        throw new CustomException(
            ErrorCode.NOTICE_REVIEW_UNAVAILABLE, "지금은 정책 제보를 받을 수 없어요. 잠시 뒤에 다시 보내 주세요");
      }
      throw e;
    }
  }

  /** 회원 제보 받기. 로그인한 회원만, 공개된 공고에만. */
  @Transactional
  public NoticeReportCreatedResponse report(
      UUID noticeId, NoticeReportRequest request, String reporter) {
    UUID reporterId = reporterId(reporter);
    if (blank(request.reportedValue()) && blank(request.note())) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "맞는 값이나 설명 중 하나는 적어 주세요");
    }
    if (reports.publishedTitle(noticeId).isEmpty()) {
      throw new CustomException(ErrorCode.NOTICE_NOT_FOUND);
    }
    Instant now = clock.instant();
    Instant todayStart = LocalDate.ofInstant(now, SEOUL).atStartOfDay(SEOUL).toInstant();
    if (reports.countSince(reporterId, todayStart) >= DAILY_LIMIT) {
      throw new CustomException(ErrorCode.RATE_LIMITED, "제보는 하루에 " + DAILY_LIMIT + "건까지 보낼 수 있어요");
    }
    UUID id = UuidV7.next();
    boolean added =
        reports.insert(
            new NoticeReportRepository.Row(
                id,
                noticeId,
                null,
                null,
                null,
                reporterId,
                request.field().trim(),
                trim(request.currentValue()),
                trim(request.reportedValue()),
                trim(request.note()),
                trim(request.screen()),
                now));
    if (!added) {
      throw new CustomException(ErrorCode.CONFLICT, "같은 칸에 보낸 제보를 아직 확인하고 있어요");
    }
    return new NoticeReportCreatedResponse(id, "NEW");
  }

  /** 회원의 창업지원 사업 제보. 판정 틀이 있는 사업(notice.policy_judgments)에만. */
  @Transactional
  public NoticeReportCreatedResponse reportProgram(
      UUID programId, NoticeReportRequest request, String reporter) {
    UUID reporterId = reporterId(reporter);
    if (blank(request.reportedValue()) && blank(request.note())) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "맞는 값이나 설명 중 하나는 적어 주세요");
    }
    if (reports.programTitle(programId).isEmpty()) {
      throw new CustomException(ErrorCode.NOT_FOUND, "창업지원 사업을 찾을 수 없어요");
    }
    Instant now = clock.instant();
    Instant todayStart = LocalDate.ofInstant(now, SEOUL).atStartOfDay(SEOUL).toInstant();
    if (reports.countSince(reporterId, todayStart) >= DAILY_LIMIT) {
      throw new CustomException(ErrorCode.RATE_LIMITED, "제보는 하루에 " + DAILY_LIMIT + "건까지 보낼 수 있어요");
    }
    UUID id = UuidV7.next();
    boolean added =
        reports.insert(
            new NoticeReportRepository.Row(
                id,
                null,
                programId,
                null,
                null,
                reporterId,
                request.field().trim(),
                trim(request.currentValue()),
                trim(request.reportedValue()),
                trim(request.note()),
                trim(request.screen()),
                now));
    if (!added) {
      throw new CustomException(ErrorCode.CONFLICT, "같은 칸에 보낸 제보를 아직 확인하고 있어요");
    }
    return new NoticeReportCreatedResponse(id, "NEW");
  }

  /**
   * 회원의 일반 제보: 공고·혜택·사업에 묶이지 않은 제보(빠진 공고·정책, 틀린 정보, 화면 오류, 기타). 대상 칸은 모두 비워 두고, 같은 종류끼리 묶지 않아요(내용이
   * 매번 달라요). 하루 제보 수 상한은 다른 제보와 같이 세요.
   */
  @Transactional
  public NoticeReportCreatedResponse reportGeneral(GeneralReportRequest request, String reporter) {
    UUID reporterId = reporterId(reporter);
    String kind = request.field().trim();
    if (!GENERAL_KINDS.contains(kind)) {
      throw new CustomException(
          ErrorCode.VALIDATION_FAILED, "field는 MISSING_NOTICE·WRONG_INFO·APP_ERROR·ETC 중 하나예요");
    }
    Instant now = clock.instant();
    Instant todayStart = LocalDate.ofInstant(now, SEOUL).atStartOfDay(SEOUL).toInstant();
    if (reports.countSince(reporterId, todayStart) >= DAILY_LIMIT) {
      throw new CustomException(ErrorCode.RATE_LIMITED, "제보는 하루에 " + DAILY_LIMIT + "건까지 보낼 수 있어요");
    }
    UUID id = UuidV7.next();
    reports.insert(
        new NoticeReportRepository.Row(
            id,
            null,
            null,
            null,
            null,
            reporterId,
            kind,
            trim(request.currentValue()),
            null,
            request.note().trim(),
            trim(request.screen()),
            now));
    return new NoticeReportCreatedResponse(id, "NEW");
  }

  /** 관리자 목록 (최근 것부터 최대 100건). status가 없으면 모두. */
  @Transactional(readOnly = true)
  public AdminReportListResponse list(String status) {
    if (status != null && !STATUSES.contains(status)) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "status는 NEW·DOING·DONE 중 하나예요");
    }
    List<AdminReportListResponse.Item> items =
        reports.list(status, LIST_LIMIT).stream().map(this::item).toList();
    return new AdminReportListResponse(counts(), items);
  }

  @Transactional(readOnly = true)
  public AdminReportListResponse.Counts counts() {
    int[] c = reports.counts();
    return new AdminReportListResponse.Counts(c[0], c[1], c[2]);
  }

  @Transactional(readOnly = true)
  public AdminReportDetailResponse detail(UUID id) {
    Report report = find(id);
    List<AdminReportDetailResponse.Note> notes = new ArrayList<>();
    for (Report other : reports.sameGroup(report, report.id())) {
      if (!blank(other.note()) || !blank(other.reportedValue())) {
        notes.add(
            new AdminReportDetailResponse.Note(
                other.reportedValue(), other.note(), other.status(), other.createdAt()));
      }
    }
    return new AdminReportDetailResponse(
        item(report),
        report.note(),
        notes,
        report.result(),
        report.reply(),
        report.handledBy(),
        report.startedAt(),
        report.handledAt(),
        report.reviewJobId());
  }

  /** 처리 시작 (새 제보 → 처리 중). 이미 처리 중·끝이면 그대로 둬요. */
  @Transactional
  public AdminReportDetailResponse start(UUID id, String admin) {
    find(id);
    reports.start(id, admin, clock.instant());
    return detail(id);
  }

  /**
   * 처리 끝. group이면 같은 공고·칸의 처리 전 제보도 같은 답으로 끝내요. 답이 있으면 제보한 회원마다 {@link NoticeReportAnswered}를 보내요.
   */
  @Transactional
  public AdminReportDetailResponse resolve(
      UUID id, AdminReportResolveRequest request, String admin) {
    Report report = find(id);
    if ("DONE".equals(report.status())) {
      throw new CustomException(ErrorCode.CONFLICT, "이미 처리한 제보예요");
    }
    List<UUID> ids = new ArrayList<>(List.of(id));
    if (request.group() == null || request.group()) {
      reports.sameGroup(report, id).stream()
          .filter(r -> !"DONE".equals(r.status()))
          .forEach(r -> ids.add(r.id()));
    }
    String reply = trim(request.reply());
    List<Report> finished =
        reports.finish(ids, request.result().name(), reply, admin, clock.instant());
    if (reply != null) {
      for (Report done : finished) {
        if (done.noticeId() == null
            && done.rawPolicyId() == null
            && done.benefitPolicyId() == null) {
          events.publishEvent(
              new GeneralReportAnswered(
                  done.id(), done.reporterId(), done.field(), done.result(), reply));
          continue;
        }
        events.publishEvent(
            done.noticeId() != null
                ? new NoticeReportAnswered(
                    done.id(),
                    done.noticeId(),
                    done.reporterId(),
                    done.field(),
                    done.result(),
                    reply,
                    done.noticeTitle())
                : done.benefitPolicyId() != null
                    ? new BenefitReportAnswered(
                        done.id(),
                        done.benefitPolicyId(),
                        done.reporterId(),
                        done.field(),
                        done.result(),
                        reply,
                        done.noticeTitle())
                    : new ProgramReportAnswered(
                        done.id(),
                        done.rawPolicyId(),
                        done.reporterId(),
                        done.field(),
                        done.result(),
                        reply,
                        done.noticeTitle()));
      }
    }
    return detail(id);
  }

  /** 탈퇴한 회원의 제보를 지워요 (요구사항 3-16). 탈퇴 트랜잭션에 함께 들어가요(커밋 직전에 불림). */
  @Transactional
  public int forget(UUID reporterId) {
    return reports.deleteByReporter(reporterId);
  }

  private Report find(UUID id) {
    return reports
        .find(id)
        .orElseThrow(() -> new CustomException(ErrorCode.NOTICE_REPORT_NOT_FOUND));
  }

  /** 목록 한 줄 (관리자 제보 대기열도 같이 써요). */
  AdminReportListResponse.Item item(Report r) {
    return new AdminReportListResponse.Item(
        r.id(),
        r.status(),
        r.screen(),
        r.noticeId() != null
            ? "NOTICE"
            : r.benefitPolicyId() != null
                ? "BENEFIT"
                : r.rawPolicyId() != null ? "PROGRAM" : "GENERAL",
        r.noticeId(),
        r.rawPolicyId(),
        r.benefitPolicyId(),
        // 제보는 원본 정책 ID로 받지만 혜택 화면은 혜택 ID를 써요
        r.benefitPolicyId() == null
            ? null
            : benefits
                .findSummaryByRawPolicyId(r.benefitPolicyId())
                .map(BenefitSummary::benefitId)
                .orElse(null),
        r.noticeTitle(),
        r.field(),
        r.currentValue(),
        r.reportedValue(),
        summary(r.note()),
        r.createdAt(),
        Math.max(r.openInGroup(), "DONE".equals(r.status()) ? 0 : 1),
        r.result());
  }

  private static UUID reporterId(String reporter) {
    if (reporter == null) {
      throw new CustomException(ErrorCode.UNAUTHENTICATED);
    }
    try {
      return UUID.fromString(reporter);
    } catch (IllegalArgumentException e) {
      throw new CustomException(ErrorCode.UNAUTHENTICATED);
    }
  }

  private static String summary(String note) {
    if (note == null) {
      return null;
    }
    String one = note.replaceAll("\\s+", " ").trim();
    return one.length() <= 40 ? one : one.substring(0, 40) + "…";
  }

  private static boolean blank(String value) {
    return value == null || value.isBlank();
  }

  private static String trim(String value) {
    return blank(value) ? null : value.trim();
  }
}
