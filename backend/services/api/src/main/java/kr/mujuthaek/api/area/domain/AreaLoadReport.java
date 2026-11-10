package kr.mujuthaek.api.area.domain;

import java.util.Map;
import java.util.UUID;

/** 적재 결과. area.load_runs 한 줄과 같아요. */
public record AreaLoadReport(
    UUID runId,
    Status status,
    int rowsIn,
    int rowsSkipped,
    int rowsRejected,
    int rowsFixed,
    int rowsInserted,
    int rowsUpdated,
    int rowsUnchanged,
    int rowsDeleted,
    Map<String, Integer> rejectReasons,
    String error) {

  public enum Status {
    SUCCEEDED,
    FAILED,
    SKIPPED
  }

  public static AreaLoadReport skipped(UUID runId) {
    return new AreaLoadReport(runId, Status.SKIPPED, 0, 0, 0, 0, 0, 0, 0, 0, Map.of(), null);
  }

  public static AreaLoadReport failed(UUID runId, String error) {
    return new AreaLoadReport(runId, Status.FAILED, 0, 0, 0, 0, 0, 0, 0, 0, Map.of(), error);
  }

  /** 테이블 내용이 바뀌었는지 (세권·점수를 다시 계산할지). */
  public boolean changedData() {
    return status == Status.SUCCEEDED && rowsInserted + rowsUpdated + rowsDeleted > 0;
  }
}
