package kr.mujuthaek.api.area.dto.response;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/** 생활권 제보 응답들. 제보한 회원이 누구인지는 보여 주지 않아요. 공고 제목은 공고 API(noticeId)로 받아요(area는 notice를 부르지 않아요). */
public final class AreaReportResponse {

  private AreaReportResponse() {}

  /** 받은 제보. */
  public record Created(UUID id, String status) {}

  /** 상태별 건수. */
  public record Counts(int newCount, int doing, int done) {}

  /**
   * 제보 한 건.
   *
   * @param groupCount 같은 공고·항목의 처리 전 제보 수 (이 제보 포함, 끝난 제보면 0)
   */
  public record Item(
      UUID id,
      String status,
      String screen,
      UUID noticeId,
      String noticeLocationId,
      String field,
      String currentValue,
      String reportedValue,
      String summary,
      OffsetDateTime createdAt,
      int groupCount,
      String result) {}

  /** 목록과 건수. */
  public record ListView(Counts counts, List<Item> items) {}

  /** 같은 항목의 다른 제보 한 줄. */
  public record Note(String reportedValue, String text, String status, OffsetDateTime createdAt) {}

  /** 상세. */
  public record Detail(
      Item report,
      String note,
      List<Note> notes,
      String result,
      String reply,
      String handledBy,
      OffsetDateTime startedAt,
      OffsetDateTime handledAt) {}
}
