package kr.mujuthaek.api.eligibility.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Clock;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitForJudgment;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.Overall;
import kr.mujuthaek.api.eligibility.rule.benefit.BenefitJudge;
import kr.mujuthaek.api.eligibility.service.BenefitEvaluationService;
import kr.mujuthaek.api.eligibility.service.CriteriaService;
import kr.mujuthaek.api.eligibility.service.NoticeBenefitService;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.json.JsonMapper;

class NoticeBenefitControllerTest {

  @Test
  void 입주지역으로_후보를_고르고_신청자_현재_거주지는_별도로_판정한다() throws Exception {
    UUID noticeId = UUID.randomUUID();
    var notices = mock(NoticeQueryService.class);
    var evaluations =
        spy(
            new BenefitEvaluationService(
                mock(BenefitQueryService.class),
                mock(CriteriaService.class),
                JsonMapper.builder().build(),
                Clock.systemUTC(),
                new SimpleMeterRegistry(),
                32));
    var notice = mock(NoticeSummary.class);
    when(notices.findSummary(noticeId)).thenReturn(Optional.of(notice));
    when(notice.field()).thenReturn("HOUSING");
    when(notice.status()).thenReturn("UPCOMING");
    when(notice.regionCodes()).thenReturn(List.of("1154500000"));

    var rent = benefit("주거급여", "RENT", true, Overall.NEEDS_INPUT);
    var denied = benefit("지원 불가", "RENT", true, Overall.INELIGIBLE);
    var undated = benefit("일정 없음", "MOVE_IN_GRANT", false, Overall.ELIGIBLE);
    var alternativeHome = benefit("다른 주거지 제공", "HOUSING_SUPPLY", true, Overall.ELIGIBLE);
    var privateOnly = benefit("민간 월세 지원", "RENT", true, Overall.NEEDS_INPUT);
    when(privateOnly.benefit().conditions())
        .thenReturn(
            List.of(
                new BenefitForJudgment.Condition(
                    "OTHER", null, 1, false, "공공임대주택(매입, 국민임대) 거주 가구 제외", null)));
    doReturn(List.of(rent, denied, undated, alternativeHome, privateOnly))
        .when(evaluations)
        .judgeAll(eq(List.of("11545")), any());

    MockMvcBuilders.standaloneSetup(
            new NoticeBenefitController(new NoticeBenefitService(notices, evaluations)))
        .build()
        .perform(
            post("/api/v1/eligibility/notices/{id}/benefits", noticeId)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{\"regionCode\":\"41360\"}}"))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.length()").value(1))
        .andExpect(jsonPath("$[0].title").value("주거급여"))
        .andExpect(jsonPath("$[0].overall").value("NEEDS_INPUT"));
    var applicant = ArgumentCaptor.forClass(Applicant.class);
    verify(evaluations).judgeAll(eq(List.of("11545")), applicant.capture());
    assertThat(applicant.getValue().regionCode()).isEqualTo("41360");
  }

  private static BenefitEvaluationService.Judged benefit(
      String title, String kind, boolean applyAlways, Overall overall) {
    var b = mock(BenefitForJudgment.class);
    when(b.id()).thenReturn(UUID.randomUUID());
    when(b.title()).thenReturn(title);
    when(b.applyAlways()).thenReturn(applyAlways);
    when(b.applyStatus(any())).thenReturn(applyAlways ? "ALWAYS" : "UNKNOWN");
    when(b.supports())
        .thenReturn(List.of(new BenefitForJudgment.Support(kind, null, null, null, null, null)));
    return new BenefitEvaluationService.Judged(
        b, new BenefitJudge.Result(overall, null, List.of(), List.of(), null), 0);
  }
}
