package kr.mujuthaek.api.chat.service;

import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;

/** 1분 5개를 넘겨 보냄 (429). 응답의 Retry-After에 다시 보낼 수 있을 때까지의 초를 실어요. */
public class ChatRateLimitedException extends CustomException {

  private final long retryAfterSeconds;

  public ChatRateLimitedException(long retryAfterSeconds) {
    super(ErrorCode.CHAT_RATE_LIMITED);
    this.retryAfterSeconds = retryAfterSeconds;
  }

  public long retryAfterSeconds() {
    return retryAfterSeconds;
  }
}
