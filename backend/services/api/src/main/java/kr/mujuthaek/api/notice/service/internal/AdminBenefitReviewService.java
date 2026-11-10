package kr.mujuthaek.api.notice.service.internal;

import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.common.cache.RecentCache;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest.FieldEdit;
import kr.mujuthaek.api.notice.dto.response.AdminBenefitReviewCountsResponse;
import kr.mujuthaek.api.notice.dto.response.AdminBenefitReviewDetailResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewDecisionResponse;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

/**
 * 관리자 혜택(주거·이주 정책) 검수 (2026-10-25). 정제 결과는 추출 서비스가 갖고 있어 그 검수 API(/benefit-reviews)를 대신 불러요.
 *
 * <p>혜택 결과는 확인 필요(needsReview) 표시와 함께 이미 나가 있어요. 승인하면 고친 결과를, 반려하면 relevant=false(서비스에 안 보임) 결과를 다시
 * 내보내요(알림 없음). 공고 검수와 같은 승인·반려 본문을 받아요.
 */
@Service
public class AdminBenefitReviewService {

  /** 대기 건수는 5초 동안 다시 써요(공고 검수 숫자와 같은 이유, {@link AdminReviewService#COUNTS_TTL}). 처리하면 바로 비워요. */
  static final Duration COUNTS_TTL = AdminReviewService.COUNTS_TTL;

  private final ExtractionReviewClient client;

  /** 키가 하나뿐인 캐시라 키는 늘 true예요. */
  private final RecentCache<Boolean, AdminBenefitReviewCountsResponse> countsCache;

  public AdminBenefitReviewService(ExtractionReviewClient client, Clock clock) {
    this.client = client;
    this.countsCache =
        new RecentCache<>(
            COUNTS_TTL, clock, k -> new AdminBenefitReviewCountsResponse(remaining()));
  }

  /** 대기 건수(사이드바·개요). 건수만 받아요. */
  public AdminBenefitReviewCountsResponse counts() {
    return countsCache.get(Boolean.TRUE);
  }

  public AdminBenefitReviewDetailResponse detail(String id) {
    JsonNode body = client.benefitDetail(id);
    JsonNode source = body.path("source");
    return new AdminBenefitReviewDetailResponse(
        text(body.path("reviewId")),
        text(body.path("rawPolicyId")),
        body.path("rawVersion").asInt(),
        text(body.path("reviewStatus")),
        strings(body.path("reasons")),
        text(body.path("note")),
        AdminReviewService.time(body.path("queuedAt")),
        AdminReviewService.time(body.path("decidedAt")),
        text(body.path("decidedBy")),
        body.path("payload"),
        body.path("edits").isNull() || body.path("edits").isMissingNode()
            ? null
            : body.path("edits"),
        new AdminBenefitReviewDetailResponse.Source(
            text(source.path("title")),
            text(source.path("agency")),
            text(source.path("detailUrl")),
            text(source.path("applyUrl")),
            strings(source.path("categories")),
            text(source.path("text")),
            text(source.path("documentStatus"))));
  }

  public AdminReviewDecisionResponse approve(
      String id, AdminReviewDecisionRequest request, String reviewer) {
    List<Map<String, Object>> edits = new ArrayList<>();
    if (request != null && request.edits() != null) {
      for (FieldEdit edit : request.edits()) {
        Map<String, Object> one = new LinkedHashMap<>();
        one.put("path", edit.path());
        one.put("value", edit.value());
        edits.add(one);
      }
    }
    client.benefitDecide(id, "approve", note(request, false), reviewer, edits);
    countsCache.clear();
    return new AdminReviewDecisionResponse(id, "APPROVED", remaining());
  }

  /** 반려: 서비스에 안 보이게 다시 내보내요. 사유가 있으면 메모 앞에 붙여 정제 결과의 relevanceReason에 남아요. */
  public AdminReviewDecisionResponse reject(
      String id, AdminReviewDecisionRequest request, String reviewer) {
    client.benefitDecide(id, "reject", note(request, true), reviewer, null);
    countsCache.clear();
    return new AdminReviewDecisionResponse(id, "REJECTED", remaining());
  }

  private static String note(AdminReviewDecisionRequest request, boolean withReason) {
    if (request == null) {
      return null;
    }
    return withReason ? AdminReviewService.rejectNote(request) : blankToNull(request.note());
  }

  private int remaining() {
    return ExtractionReviewClient.total(client.benefitPendingHead());
  }

  private static String blankToNull(String value) {
    return value == null || value.isBlank() ? null : value.trim();
  }

  private static String text(JsonNode node) {
    return node == null || node.isNull() || node.isMissingNode() ? null : node.asString();
  }

  private static List<String> strings(JsonNode node) {
    List<String> out = new ArrayList<>();
    if (node != null && node.isArray()) {
      node.forEach(value -> out.add(value.asString()));
    }
    return out;
  }

  /** 시험·다른 서비스에서 쓰는 시각 변환을 공고 검수와 맞춰요. */
  static OffsetDateTime time(JsonNode node) {
    return AdminReviewService.time(node);
  }
}
