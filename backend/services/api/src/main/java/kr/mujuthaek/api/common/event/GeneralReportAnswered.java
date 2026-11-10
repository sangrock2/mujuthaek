package kr.mujuthaek.api.common.event;

import java.util.UUID;

/**
 * 관리자가 일반 제보(공고·혜택·사업에 묶이지 않은 제보)를 처리하고 답을 남김. 가리킬 대상이 없어 알림함에만 남고 내 정보의 제보 탭으로 가요.
 *
 * @param result FIXED 고침 · KEPT 그대로 둠
 */
public record GeneralReportAnswered(
    UUID reportId, UUID reporterId, String field, String result, String reply)
    implements ReportAnswered {

  @Override
  public String targetTitle() {
    return null;
  }
}
