package kr.mujuthaek.api.notice.domain;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

/**
 * 접수 기간과 지금 시각으로 접수 상태를 계산해요. 스프링·DB 없이 값만 보고 정해요.
 *
 * <ul>
 *   <li>날짜만 있는 마감일은 그날 한국 시간이 끝날 때까지 접수 중이에요(원문에 없는 23:59를 만들지 않아요).
 *   <li>원문에 시각이 있으면(「10/30 17:00까지」) 그 시각까지만 접수 중이에요(리뷰 2026-10-22: 날짜로 줄여 그날 자정까지 접수 중이었음).
 *   <li>접수 기간 사이(10/20~21, 10/25~26의 10/23)는 다음 기간이 남아 있어 UPCOMING이에요.
 *   <li>마감일이 없다는 이유만으로 상시 모집으로 보지 않아요. 상시 모집은 원문에 명시된 경우(rolling)만이에요.
 *   <li>날짜를 모르는 기간(확인 전까지 보류한 구간 포함)이 있으면 마감으로 단정하지 않고 UNKNOWN이에요.
 * </ul>
 */
public final class ApplicationStatusCalculator {

  public static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

  /** 시각까지 있는 마감은 마감 시각 1분 뒤에 다시 계산해요. */
  private static final Duration AFTER_DEADLINE = Duration.ofMinutes(1);

  private ApplicationStatusCalculator() {}

  /**
   * 접수 기간 하나. 시작·마감 날짜는 모르면 null. startsAt·endsAt은 원문에 시각까지 있을 때만(없으면 null) 쓰고, 그때도
   * 날짜(startOn·endOn)는 함께 채워요(목록·마감일 표시용).
   */
  public record Window(LocalDate startOn, LocalDate endOn, Instant startsAt, Instant endsAt) {

    public Window(LocalDate startOn, LocalDate endOn) {
      this(startOn, endOn, null, null);
    }

    boolean known() {
      return startOn != null || endOn != null;
    }

    boolean started(Instant now, LocalDate today) {
      return startsAt != null
          ? !now.isBefore(startsAt)
          : startOn != null && !today.isBefore(startOn);
    }

    boolean notEnded(Instant now, LocalDate today) {
      return endsAt != null ? !now.isAfter(endsAt) : endOn == null || !today.isAfter(endOn);
    }

    boolean hasEnd() {
      return endsAt != null || endOn != null;
    }

    boolean startsLater(Instant now, LocalDate today) {
      return startsAt != null ? startsAt.isAfter(now) : startOn != null && startOn.isAfter(today);
    }

    boolean ended(Instant now, LocalDate today) {
      return endsAt != null ? now.isAfter(endsAt) : endOn != null && endOn.isBefore(today);
    }
  }

  /** 계산 결과. nextCheckAt은 상태가 바뀔 수 있는 다음 시각(없으면 null). */
  public record Result(NoticeStatus status, Instant nextCheckAt) {}

  /** 날짜만으로 계산(그날 0시 기준). 시각이 있는 구간은 {@link #calculate(List, boolean, Instant)}를 써요. */
  public static Result calculate(List<Window> windows, boolean rolling, LocalDate today) {
    return calculate(windows, rolling, today.atStartOfDay(KOREA).toInstant());
  }

  public static Result calculate(List<Window> windows, boolean rolling, Instant now) {
    LocalDate today = LocalDate.ofInstant(now, KOREA);
    List<Window> known = windows.stream().filter(Window::known).toList();
    // 날짜를 모르는 기간이 있으면 남은 접수가 있을 수 있어 마감으로 단정하지 않아요
    boolean undated = known.size() < windows.size();
    NoticeStatus status = status(known, rolling, undated, now, today);
    return new Result(status, nextCheck(known, now, today));
  }

  private static NoticeStatus status(
      List<Window> windows, boolean rolling, boolean undated, Instant now, LocalDate today) {
    if (windows.isEmpty()) {
      return rolling ? NoticeStatus.ALWAYS : NoticeStatus.UNKNOWN;
    }
    boolean unknownOpen = false;
    for (Window w : windows) {
      boolean started = w.started(now, today);
      boolean notEnded = w.notEnded(now, today);
      if (started && w.hasEnd() && notEnded) {
        return NoticeStatus.APPLYING;
      }
      if (started && !w.hasEnd()) {
        if (rolling) {
          return NoticeStatus.ALWAYS;
        }
        unknownOpen = true; // 시작은 했는데 마감을 모름
      }
      if (w.startOn() == null && w.startsAt() == null && notEnded) {
        unknownOpen = true; // 마감 전인데 시작을 모름
      }
    }
    if (unknownOpen) {
      return NoticeStatus.UNKNOWN;
    }
    if (windows.stream().anyMatch(w -> w.startsLater(now, today))) {
      return NoticeStatus.UPCOMING;
    }
    boolean allEnded = windows.stream().allMatch(w -> w.ended(now, today));
    return allEnded && !undated ? NoticeStatus.CLOSED : NoticeStatus.UNKNOWN;
  }

  /** 마감 알림(NoticeClosed)을 보낼 변화인지: 마감이 아니던 공고가 마감으로 바뀜. 처음부터 마감인 공고는 이전 상태가 없어 보내지 않아요. */
  public static boolean justClosed(NoticeStatus before, NoticeStatus after) {
    return before != null && before != NoticeStatus.CLOSED && after == NoticeStatus.CLOSED;
  }

  /** 마감일: 접수 기간 중 가장 늦은 마감일. 마감일을 모르면 오늘. */
  public static LocalDate closedOn(List<Window> windows, LocalDate today) {
    return windows.stream()
        .map(Window::endOn)
        .filter(Objects::nonNull)
        .max(LocalDate::compareTo)
        .orElse(today);
  }

  /** 다음에 상태가 바뀔 수 있는 시각: 시작(시각 또는 그날 0시), 마감 뒤(마감 시각 1분 뒤 또는 마감 다음 날 0시). */
  private static Instant nextCheck(List<Window> windows, Instant now, LocalDate today) {
    return windows.stream()
        .flatMap(w -> Stream.of(start(w), afterEnd(w)))
        .filter(Objects::nonNull)
        .filter(at -> at.isAfter(now))
        .min(Instant::compareTo)
        .orElse(null);
  }

  private static Instant start(Window w) {
    if (w.startsAt() != null) {
      return w.startsAt();
    }
    return w.startOn() == null ? null : w.startOn().atStartOfDay(KOREA).toInstant();
  }

  private static Instant afterEnd(Window w) {
    if (w.endsAt() != null) {
      return w.endsAt().plus(AFTER_DEADLINE);
    }
    return w.endOn() == null ? null : w.endOn().plusDays(1).atStartOfDay(KOREA).toInstant();
  }
}
