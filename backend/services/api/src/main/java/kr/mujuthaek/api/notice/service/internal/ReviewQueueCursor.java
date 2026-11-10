package kr.mujuthaek.api.notice.service.internal;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Base64;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient.After;

/**
 * 관리자 검수 대기열의 다음 페이지 위치: 공고·혜택 쪽마다 마지막으로 보낸 건(들어온 시각·ID)과 다 받았는지. 주소에 넣기 좋게 base64url로 묶어요 (화면은 값을
 * 읽지 않고 그대로 돌려보내요).
 */
record ReviewQueueCursor(Side notice, Side benefit) {

  static final ReviewQueueCursor START = new ReviewQueueCursor(Side.START, Side.START);

  /** 한 쪽의 위치. after가 null이면 처음부터, done이면 더 받을 게 없어요. */
  record Side(After after, boolean done) {

    static final Side START = new Side(null, false);
    static final Side DONE = new Side(null, true);

    private String encode() {
      return done ? "-" : after == null ? "" : after.at() + "," + after.id();
    }

    private static Side decode(String value) {
      if (value.equals("-")) {
        return DONE;
      }
      if (value.isEmpty()) {
        return START;
      }
      String[] parts = value.split(",", -1);
      if (parts.length != 2) {
        throw new IllegalArgumentException();
      }
      return new Side(
          new After(Instant.parse(parts[0]), UUID.fromString(parts[1]).toString()), false);
    }
  }

  String encode() {
    String value = notice.encode() + "|" + benefit.encode();
    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(value.getBytes(StandardCharsets.UTF_8));
  }

  /** 비었으면 처음부터. 형식이 틀리면 400. */
  static ReviewQueueCursor decode(String value) {
    if (value == null || value.isBlank()) {
      return START;
    }
    try {
      String raw = new String(Base64.getUrlDecoder().decode(value), StandardCharsets.UTF_8);
      String[] sides = raw.split("\\|", -1);
      if (sides.length != 2) {
        throw new IllegalArgumentException();
      }
      return new ReviewQueueCursor(Side.decode(sides[0]), Side.decode(sides[1]));
    } catch (IllegalArgumentException | DateTimeParseException e) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "cursor가 올바르지 않아요");
    }
  }
}
