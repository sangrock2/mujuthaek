package kr.mujuthaek.api.chat.controller;

import jakarta.servlet.http.HttpServletRequest;
import kr.mujuthaek.api.chat.service.ChatRateLimitedException;
import kr.mujuthaek.api.common.exception.Problems;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 429에 Retry-After 헤더를 더해요 (화면은 그 초만큼 입력을 막아요). 나머지 오류는 공통 처리(GlobalExceptionHandler)가 맡아요. 같은 오류를
 * 공통 처리보다 먼저 받으려고 순서를 가장 앞에 둬요.
 */
@RestControllerAdvice(assignableTypes = ChatController.class)
@Order(Ordered.HIGHEST_PRECEDENCE)
class ChatExceptionHandler {

  @ExceptionHandler(ChatRateLimitedException.class)
  ResponseEntity<ProblemDetail> rateLimited(
      ChatRateLimitedException e, HttpServletRequest request) {
    return ResponseEntity.status(e.errorCode().status())
        .header(HttpHeaders.RETRY_AFTER, String.valueOf(e.retryAfterSeconds()))
        .body(Problems.of(e.errorCode(), e.getMessage(), request));
  }
}
