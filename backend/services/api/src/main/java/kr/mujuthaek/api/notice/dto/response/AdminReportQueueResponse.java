package kr.mujuthaek.api.notice.dto.response;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/**
 * 관리자 제보 대기열 한 페이지: 공고·혜택·사업 제보와 생활권 제보를 들어온 시각 최신순으로 섞어요. 다음 페이지는 nextCursor를 그대로 보내요(없으면 끝).
 *
 * @param items 이 페이지의 제보
 * @param nextCursor 다음 페이지 위치, 다 받았으면 null
 */
public record AdminReportQueueResponse(List<Item> items, String nextCursor) {

  /**
   * 제보 한 건.
   *
   * @param kind REPORT 공고·혜택·사업·일반 제보(/api/admin/reports/{id}) · AREA 생활권
   *     제보(/api/admin/area-reports/{id})
   * @param targetType NOTICE · PROGRAM · BENEFIT · GENERAL · AREA(생활권)
   * @param title 무엇에 대한 제보인지: 공고·사업·혜택 이름, 생활권 제보는 「공고 이름 · 단지 이름」(못 찾으면 null)
   * @param noticeLocationId 생활권 제보가 가리키는 단지(공고 위치) ID, 그 밖이면 null
   * @param groupCount 같은 대상·칸의 처리 전 제보 수 (이 제보 포함, 끝난 제보면 0)
   * @param result 처리 결과 FIXED · KEPT (끝나기 전엔 null)
   */
  public record Item(
      String kind,
      UUID id,
      String status,
      String screen,
      String targetType,
      UUID noticeId,
      String noticeLocationId,
      UUID programId,
      UUID benefitPolicyId,
      UUID benefitId,
      String title,
      String field,
      String currentValue,
      String reportedValue,
      String summary,
      OffsetDateTime createdAt,
      int groupCount,
      String result) {}
}
