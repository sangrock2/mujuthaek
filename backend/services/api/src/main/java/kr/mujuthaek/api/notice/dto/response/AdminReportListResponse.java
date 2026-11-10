package kr.mujuthaek.api.notice.dto.response;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/** 관리자 제보 목록 (최근 것부터 최대 100건)과 상태별 건수. */
public record AdminReportListResponse(Counts counts, List<Item> items) {

  /** 상태별 전체 건수 (사이드바·탭 숫자). */
  public record Counts(int newCount, int doing, int done) {}

  /**
   * 제보 한 건.
   *
   * @param status NEW 새 제보 · DOING 처리 중 · DONE 처리 끝
   * @param screen 제보한 화면
   * @param targetType NOTICE 공고 제보 · PROGRAM 창업지원 사업 제보 · BENEFIT 주거·복지 정책(혜택) 제보
   * @param noticeId 공고 제보면 공고 ID (사업이면 null)
   * @param programId 사업 제보면 창업지원 사업 ID(rawPolicyId) (공고면 null)
   * @param benefitPolicyId 혜택 정책 제보면 정책 원본 ID (그 밖이면 null). 「고치기」는 혜택
   *     검수(/api/admin/benefit-reviews)로 이어져요
   * @param benefitId 혜택 화면(/benefits/{id})에 쓰는 혜택 ID. 원본 정책 ID와 달라요. 혜택 제보가 아니거나 아직 저장 전이면 null
   * @param field 칸 이름
   * @param summary 설명 앞부분
   * @param groupCount 같은 공고·칸의 처리 전 제보 수 (이 제보 포함, 끝난 제보면 0)
   * @param result 처리 결과 FIXED · KEPT (끝나기 전엔 null)
   */
  public record Item(
      UUID id,
      String status,
      String screen,
      String targetType,
      UUID noticeId,
      UUID programId,
      UUID benefitPolicyId,
      UUID benefitId,
      String noticeTitle,
      String field,
      String currentValue,
      String reportedValue,
      String summary,
      OffsetDateTime createdAt,
      int groupCount,
      String result) {}
}
