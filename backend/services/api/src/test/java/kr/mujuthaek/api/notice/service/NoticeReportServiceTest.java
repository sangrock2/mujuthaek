package kr.mujuthaek.api.notice.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.common.event.NoticeReportAnswered;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.client.ExtractionReviewProperties;
import kr.mujuthaek.api.notice.dto.request.AdminReportResolveRequest;
import kr.mujuthaek.api.notice.dto.request.AdminReportResolveRequest.Result;
import kr.mujuthaek.api.notice.dto.request.NoticeReportRequest;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository;
import kr.mujuthaek.api.notice.service.internal.NoticeReportService;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

/** 공고 제보: 회원이 보내고 관리자가 처리해 답을 남기는 흐름 (실제 DB). */
class NoticeReportServiceTest {

  private final NoticeApiFixture fixture = new NoticeApiFixture();
  private final List<Object> events = new ArrayList<>();
  private final kr.mujuthaek.api.benefit.service.BenefitQueryService benefits =
      org.mockito.Mockito.mock(kr.mujuthaek.api.benefit.service.BenefitQueryService.class);
  private final NoticeReportService service =
      new NoticeReportService(
          new NoticeReportRepository(JdbcClient.create(fixture.jdbc)),
          reviewClient(),
          events::add,
          Clock.fixed(Instant.parse("2026-10-25T03:00:00Z"), ZoneId.of("Asia/Seoul")),
          benefits);

  private MockRestServiceServer reviewServer;

  private ExtractionReviewClient reviewClient() {
    var builder = RestClient.builder();
    reviewServer = MockRestServiceServer.bindTo(builder).build();
    return new ExtractionReviewClient(
        new ExtractionReviewProperties("http://extraction.test", null, Duration.ofSeconds(1)),
        builder);
  }

  private static NoticeReportRequest deposit(String note) {
    return new NoticeReportRequest("보증금", "2,400만 원", "2,600만 원", note, "공고 상세");
  }

  private UUID notice() {
    return fixture.notice(p -> {});
  }

  @Test
  void reportIsListedAsNewWithGroupCount() {
    UUID notice = notice();
    String a = UUID.randomUUID().toString();
    String b = UUID.randomUUID().toString();
    UUID first = service.report(notice, deposit("공고문 4쪽"), a).id();
    service.report(notice, deposit("정정 공고에 2,600만 원"), b);

    var detail = service.detail(first);
    assertThat(detail.report().status()).isEqualTo("NEW");
    assertThat(detail.report().groupCount()).isEqualTo(2);
    assertThat(detail.report().noticeId()).isEqualTo(notice);
    assertThat(detail.notes()).extracting(n -> n.text()).containsExactly("정정 공고에 2,600만 원");
    assertThat(service.list("NEW").items()).extracting(i -> i.id()).contains(first);
  }

  @Test
  void generalReportsAreNotGroupedAndAnsweredWithoutTarget() {
    UUID a = UUID.randomUUID();
    UUID b = UUID.randomUUID();
    var first =
        service.reportGeneral(
            new kr.mujuthaek.api.notice.dto.request.GeneralReportRequest(
                "MISSING_NOTICE", "마포구 청년주택 공고가 없어요", "검색", null),
            a.toString());
    service.reportGeneral(
        new kr.mujuthaek.api.notice.dto.request.GeneralReportRequest(
            "MISSING_NOTICE", "다른 공고도 빠졌어요", "검색", null),
        b.toString());
    // 같은 사람이 같은 종류를 또 보내도 돼요 (내용이 매번 달라요)
    service.reportGeneral(
        new kr.mujuthaek.api.notice.dto.request.GeneralReportRequest(
            "MISSING_NOTICE", "하나 더", null, null),
        a.toString());

    var detail = service.detail(first.id());
    assertThat(detail.report().targetType()).isEqualTo("GENERAL");
    assertThat(detail.report().groupCount()).isEqualTo(1); // 같은 종류끼리 묶지 않아요
    assertThat(detail.notes()).isEmpty();
    assertThatThrownBy(() -> service.openReview(first.id(), "admin-1"))
        .isInstanceOfSatisfying(
            CustomException.class, e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.CONFLICT));

    service.resolve(
        first.id(), new AdminReportResolveRequest(Result.FIXED, "공고를 더했어요", null), "admin-1");
    // 묶음 처리(group 기본값)여도 다른 사람의 일반 제보는 그대로예요
    assertThat(events)
        .singleElement()
        .isInstanceOfSatisfying(
            kr.mujuthaek.api.common.event.GeneralReportAnswered.class,
            e -> assertThat(e.reporterId()).isEqualTo(a));
    assertThat(service.list("NEW").items())
        .filteredOn(i -> "GENERAL".equals(i.targetType()))
        .hasSize(2);
  }

  @Test
  void generalReportNeedsKnownKindNoteAndLogin() {
    assertThatThrownBy(
            () ->
                service.reportGeneral(
                    new kr.mujuthaek.api.notice.dto.request.GeneralReportRequest(
                        "HELLO", "내용", null, null),
                    UUID.randomUUID().toString()))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.VALIDATION_FAILED));
    assertThatThrownBy(
            () ->
                service.reportGeneral(
                    new kr.mujuthaek.api.notice.dto.request.GeneralReportRequest(
                        "ETC", "내용", null, null),
                    null))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.UNAUTHENTICATED));
  }

  @Test
  void sameMemberCannotReportSameFieldTwiceWhileOpen() {
    UUID notice = notice();
    String a = UUID.randomUUID().toString();
    service.report(notice, deposit("첫 제보"), a);
    assertThatThrownBy(() -> service.report(notice, deposit("또"), a))
        .isInstanceOfSatisfying(
            CustomException.class, e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.CONFLICT));
  }

  @Test
  void anonymousUnknownNoticeAndEmptyReportAreRefused() {
    UUID notice = notice();
    assertThatThrownBy(() -> service.report(notice, deposit("x"), null))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.UNAUTHENTICATED));
    assertThatThrownBy(
            () -> service.report(UUID.randomUUID(), deposit("x"), UUID.randomUUID().toString()))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOTICE_NOT_FOUND));
    var empty = new NoticeReportRequest("보증금", "2,400만 원", " ", null, null);
    assertThatThrownBy(() -> service.report(notice, empty, UUID.randomUUID().toString()))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.VALIDATION_FAILED));
  }

  @Test
  void resolvingTheGroupAnswersEveryReporter() {
    UUID notice = notice();
    UUID a = UUID.randomUUID();
    UUID b = UUID.randomUUID();
    UUID first = service.report(notice, deposit("4쪽"), a.toString()).id();
    service.report(notice, deposit("정정"), b.toString());

    service.start(first, "admin-1");
    assertThat(service.detail(first).report().status()).isEqualTo("DOING");

    var done =
        service.resolve(
            first, new AdminReportResolveRequest(Result.FIXED, "보증금을 고쳤어요", null), "admin-1");
    assertThat(done.report().status()).isEqualTo("DONE");
    assertThat(done.result()).isEqualTo("FIXED");
    assertThat(done.handledBy()).isEqualTo("admin-1");
    assertThat(done.notes()).allMatch(n -> n.status().equals("DONE"));
    assertThat(events)
        .extracting(e -> ((NoticeReportAnswered) e).reporterId())
        .containsExactlyInAnyOrder(a, b);
    // 알림 쪽이 문구에 쓰는 대상 제목도 함께 실어요
    assertThat(events)
        .extracting(e -> ((NoticeReportAnswered) e).targetTitle())
        .containsOnly(service.detail(first).report().noticeTitle())
        .doesNotContainNull();
    assertThatThrownBy(
            () ->
                service.resolve(
                    first, new AdminReportResolveRequest(Result.KEPT, null, false), "admin-1"))
        .isInstanceOfSatisfying(
            CustomException.class, e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.CONFLICT));
  }

  @Test
  void resolvingWithoutReplySendsNothingAndCanSkipGroup() {
    UUID notice = notice();
    UUID first = service.report(notice, deposit("4쪽"), UUID.randomUUID().toString()).id();
    UUID second = service.report(notice, deposit("정정"), UUID.randomUUID().toString()).id();
    service.resolve(first, new AdminReportResolveRequest(Result.KEPT, " ", false), "admin-1");
    assertThat(events).isEmpty();
    assertThat(service.detail(second).report().status()).isEqualTo("NEW");
  }

  @Test
  void withdrawnMembersReportsAreDeleted() {
    UUID notice = notice();
    UUID member = UUID.randomUUID();
    UUID id = service.report(notice, deposit("4쪽"), member.toString()).id();
    assertThat(service.forget(member)).isEqualTo(1);
    assertThatThrownBy(() -> service.detail(id))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOTICE_REPORT_NOT_FOUND));
  }

  @Test
  void fixOpensTheNoticeResultForReviewAndLinksTheGroup() {
    UUID notice = notice();
    UUID rawPost =
        fixture.jdbc.queryForObject(
            "select current_raw_post_id from notice.notices where id = ?", UUID.class, notice);
    UUID first = service.report(notice, deposit("4쪽"), UUID.randomUUID().toString()).id();
    UUID second = service.report(notice, deposit("정정"), UUID.randomUUID().toString()).id();
    UUID job = UUID.randomUUID();
    reviewServer
        .expect(requestTo("http://extraction.test/reviews/reopen"))
        .andExpect(
            content()
                .json(
                    "{\"rawPostId\":\""
                        + rawPost
                        + "\",\"reviewer\":\"admin-1\",\"note\":\"공고 제보: 보증금\"}"))
        .andRespond(
            withSuccess(
                "{\"jobId\":\"" + job + "\",\"reviewStatus\":\"PENDING\",\"reopened\":true}",
                MediaType.APPLICATION_JSON));

    var opened = service.openReview(first, "admin-1");

    assertThat(opened.reviewId()).isEqualTo(job);
    assertThat(opened.reopened()).isTrue();
    assertThat(service.detail(first).reviewId()).isEqualTo(job);
    assertThat(service.detail(first).report().status()).isEqualTo("DOING");
    assertThat(service.detail(second).reviewId()).isEqualTo(job);
    reviewServer.verify();
  }

  @Test
  void startupProgramsCanBeReportedAndAnsweredButNotReopened() {
    UUID program = UUID.randomUUID();
    fixture.jdbc.update(
        "insert into notice.policy_judgments (raw_policy_id, field, raw_version, source_event_id,"
            + " title, region_codes, frame, created_at, updated_at) values (?, 'STARTUP_SUPPORT',"
            + " 1, ?, '가상 예비창업 지원', '{}', '{}'::jsonb, now(), now())",
        program,
        UUID.randomUUID());
    UUID reporter = UUID.randomUUID();
    UUID id = service.reportProgram(program, deposit("공고문 2쪽"), reporter.toString()).id();

    var detail = service.detail(id);
    assertThat(detail.report().targetType()).isEqualTo("PROGRAM");
    assertThat(detail.report().programId()).isEqualTo(program);
    assertThat(detail.report().noticeTitle()).isEqualTo("가상 예비창업 지원");
    assertThatThrownBy(() -> service.openReview(id, "admin-1"))
        .isInstanceOfSatisfying(
            CustomException.class, e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.CONFLICT));
    assertThatThrownBy(
            () -> service.reportProgram(UUID.randomUUID(), deposit("x"), reporter.toString()))
        .isInstanceOfSatisfying(
            CustomException.class, e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOT_FOUND));

    service.resolve(id, new AdminReportResolveRequest(Result.KEPT, "공고문대로예요", null), "admin-1");
    assertThat(events)
        .singleElement()
        .isInstanceOfSatisfying(
            kr.mujuthaek.api.common.event.ProgramReportAnswered.class,
            e -> {
              assertThat(e.programId()).isEqualTo(program);
              assertThat(e.targetTitle()).isEqualTo("가상 예비창업 지원");
            });
  }

  @Test
  void benefitReportUsesTheBenefitTitleHereWithoutAskingExtraction() {
    // 운영 결과를 받아 쓰는 개발 서버처럼 추출 서비스에 그 정책이 없어도 이 서버에 혜택이 있으면 제보를 받아요(2026-10-29 QA)
    UUID policy = UUID.randomUUID();
    UUID benefitId = UUID.randomUUID();
    org.mockito.Mockito.when(benefits.findRawPolicyId(benefitId))
        .thenReturn(java.util.Optional.of(policy));
    org.mockito.Mockito.when(benefits.findSummaryByRawPolicyId(policy))
        .thenReturn(
            java.util.Optional.of(
                new kr.mujuthaek.api.benefit.service.BenefitSummary(
                    benefitId,
                    "HOUSING",
                    1,
                    "가상 이사비 지원",
                    "가상구청",
                    "OPEN",
                    null,
                    null,
                    true,
                    "NATIONWIDE",
                    java.util.List.of(),
                    null)));

    UUID id =
        service.reportBenefit(benefitId, deposit("공고문 2쪽"), UUID.randomUUID().toString()).id();

    assertThat(service.detail(id).report().noticeTitle()).isEqualTo("가상 이사비 지원");
    reviewServer.verify(); // 추출 서비스에는 묻지 않았어요
  }

  @Test
  void benefitPoliciesAreReportedReopenedAsBenefitReviewsAndAnswered() {
    UUID policy = UUID.randomUUID();
    UUID missing = UUID.fromString(policy.toString().replace('0', '1'));
    UUID review = UUID.randomUUID();
    // 가짜 추출 서버는 요청이 오기 전에 기대를 모두 적어야 해요(요청 뒤에는 더할 수 없음)
    reviewServer
        .expect(requestTo("http://extraction.test/benefits/" + policy))
        .andRespond(withSuccess("{\"title\":\"가상 청년 월세\"}", MediaType.APPLICATION_JSON));
    reviewServer
        .expect(requestTo("http://extraction.test/benefit-reviews/reopen"))
        .andExpect(content().json("{\"rawPolicyId\":\"" + policy + "\",\"reviewer\":\"admin-1\"}"))
        .andRespond(
            withSuccess(
                "{\"reviewId\":\"" + review + "\",\"reopened\":true}", MediaType.APPLICATION_JSON));
    reviewServer
        .expect(requestTo("http://extraction.test/benefits/" + missing))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));

    UUID reporter = UUID.randomUUID();
    // 혜택 화면은 혜택 ID를 써요: 원본 정책 ID로 바꿔 받아요
    UUID benefitId = UUID.randomUUID();
    org.mockito.Mockito.when(benefits.findRawPolicyId(benefitId))
        .thenReturn(java.util.Optional.of(policy));
    UUID id = service.reportBenefit(benefitId, deposit("공고문 3쪽"), reporter.toString()).id();

    var detail = service.detail(id);
    assertThat(detail.report().targetType()).isEqualTo("BENEFIT");
    assertThat(detail.report().benefitPolicyId()).isEqualTo(policy);
    assertThat(detail.report().noticeTitle()).isEqualTo("가상 청년 월세");

    assertThat(service.openReview(id, "admin-1").reviewId()).isEqualTo(review);

    assertThatThrownBy(() -> service.reportBenefit(missing, deposit("x"), reporter.toString()))
        .isInstanceOfSatisfying(
            CustomException.class, e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOT_FOUND));

    service.resolve(id, new AdminReportResolveRequest(Result.FIXED, "고쳤어요", null), "admin-1");
    assertThat(events)
        .singleElement()
        .isInstanceOfSatisfying(
            kr.mujuthaek.api.common.event.BenefitReportAnswered.class,
            e -> {
              assertThat(e.policyId()).isEqualTo(policy);
              assertThat(e.targetTitle()).isEqualTo("가상 청년 월세");
            });
    reviewServer.verify();
  }
}
