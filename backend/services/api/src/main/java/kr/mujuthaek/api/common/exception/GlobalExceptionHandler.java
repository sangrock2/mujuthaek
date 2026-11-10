package kr.mujuthaek.api.common.exception;

import jakarta.servlet.http.HttpServletRequest;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Locale;
import kr.mujuthaek.api.common.alert.OpsAlert;
import kr.mujuthaek.api.common.logging.SensitiveFields;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.async.AsyncRequestNotUsableException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * 오류 응답 형식 통일: Problem Details(RFC 9457) + 화면이 문구를 고를 {@code code}.
 *
 * <pre>
 * { "type": "https://mujuthaek.kr/problems/validation-failed", "title": "입력값이 올바르지 않아요",
 *   "status": 400, "code": "VALIDATION_FAILED", "detail": "…", "instance": "/api/v1/…",
 *   "errors": [{ "field": "applicant.assets.gtWon", "reason": "MIN" }] }
 * </pre>
 *
 * <p>입력값(소득·자산 등)은 detail·errors·로그 어디에도 넣지 않아요. 칸 이름과 어긴 규칙만 남겨요. 500은 코드와 시각만 보여줘요.
 */
@RestControllerAdvice
class GlobalExceptionHandler {

  private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);
  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

  /** 처리하지 못한 오류·5xx를 슬랙으로 알려요. 시험에서 new로 만들면 없어요. */
  private final OpsAlert alert;

  GlobalExceptionHandler() {
    this(null);
  }

  @Autowired
  GlobalExceptionHandler(OpsAlert alert) {
    this.alert = alert;
  }

  /** errors[] 한 칸. reason은 어긴 검사 이름(Min → MIN, NotNull → NOT_NULL). */
  record FieldProblem(String field, String reason) {}

  @ExceptionHandler(CustomException.class)
  ProblemDetail handle(CustomException e, HttpServletRequest request) {
    if (e.errorCode().status().is5xxServerError()
        && (alert == null || !alert.ignores(e.errorCode().name()))) {
      // 다른 서비스(검수·수집기·알림 서버) 연결 실패 같은 서버 쪽 문제. 코드별로 묶어 알려요
      notify(
          "api.5xx:" + e.errorCode().name(),
          e.errorCode().name() + " " + request.getMethod() + " " + request.getRequestURI(),
          e.errorCode().message());
    }
    return problem(e.errorCode(), e.getMessage(), request);
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  ProblemDetail handle(MethodArgumentNotValidException e, HttpServletRequest request) {
    List<FieldError> errors = e.getBindingResult().getFieldErrors();
    String detail =
        errors.stream()
            .findFirst()
            .map(error -> error.getField() + ": " + error.getDefaultMessage())
            .orElse(ErrorCode.VALIDATION_FAILED.message());
    ProblemDetail problem = problem(ErrorCode.VALIDATION_FAILED, detail, request);
    problem.setProperty(
        "errors",
        errors.stream()
            .map(error -> new FieldProblem(error.getField(), reason(error.getCode())))
            .toList());
    return problem;
  }

  @ExceptionHandler(HandlerMethodValidationException.class)
  ProblemDetail handle(HandlerMethodValidationException e, HttpServletRequest request) {
    List<FieldProblem> errors =
        e.getParameterValidationResults().stream()
            .flatMap(
                result ->
                    result.getResolvableErrors().stream()
                        .map(
                            error ->
                                new FieldProblem(
                                    result.getMethodParameter().getParameterName(),
                                    reason(lastCode(error.getCodes())))))
            .toList();
    ProblemDetail problem =
        problem(ErrorCode.VALIDATION_FAILED, ErrorCode.VALIDATION_FAILED.message(), request);
    problem.setProperty("errors", errors);
    return problem;
  }

  @ExceptionHandler({
    HttpMessageNotReadableException.class,
    MethodArgumentTypeMismatchException.class,
    MissingServletRequestParameterException.class
  })
  ProblemDetail handleUnreadable(Exception e, HttpServletRequest request) {
    String detail =
        switch (e) {
          case MethodArgumentTypeMismatchException m -> m.getName() + ": 형식이 맞지 않아요";
          case MissingServletRequestParameterException m -> m.getParameterName() + ": 꼭 있어야 해요";
          default -> "요청 본문을 읽지 못했어요 (JSON 형식 확인)";
        };
    return problem(ErrorCode.VALIDATION_FAILED, detail, request);
  }

  @ExceptionHandler(NoResourceFoundException.class)
  ProblemDetail handle(NoResourceFoundException e, HttpServletRequest request) {
    return problem(ErrorCode.NOT_FOUND, ErrorCode.NOT_FOUND.message(), request);
  }

  /** 받는 쪽이 먼저 연결을 끊은 비동기 응답(채팅 SSE 등: 탭을 닫거나 화면을 떠남). 보낼 곳이 없어 응답하지 않고, 서버 오류도 아니라 알리지 않아요. */
  @ExceptionHandler(AsyncRequestNotUsableException.class)
  void handleDisconnected(AsyncRequestNotUsableException e, HttpServletRequest request) {
    log.debug("받는 쪽이 연결을 끊었어요: {} {}", request.getMethod(), request.getRequestURI());
  }

  @ExceptionHandler(Exception.class)
  ResponseEntity<ProblemDetail> handle(Exception e, HttpServletRequest request) {
    if (e instanceof ErrorResponse standard && standard.getStatusCode().is4xxClientError()) {
      // 스프링 표준 요청 오류(405·415·406·404 등)는 서버 오류가 아니에요: 원래 상태 코드와 헤더(Allow·Accept)를 그대로 돌려줘요
      return ResponseEntity.status(standard.getStatusCode())
          .headers(standard.getHeaders())
          .body(clientProblem(standard.getStatusCode(), request));
    }
    // 예외 메시지에 판정 입력 값이 섞여 있을 수 있어서 가린 뒤에 남겨요
    log.error(
        "처리하지 못한 오류: {} {}",
        request.getMethod(),
        request.getRequestURI(),
        SensitiveFields.masked(e));
    notify(
        "api.unhandled:" + e.getClass().getName(),
        "처리하지 못한 오류 " + request.getMethod() + " " + request.getRequestURI(),
        e.getClass().getSimpleName());
    ProblemDetail problem =
        problem(ErrorCode.INTERNAL_ERROR, ErrorCode.INTERNAL_ERROR.message(), request);
    problem.setProperty("timestamp", OffsetDateTime.now(SEOUL).withNano(0).toString());
    return ResponseEntity.status(problem.getStatus()).body(problem);
  }

  /** 스프링 표준 4xx 오류를 우리 코드로. 맞는 코드가 없으면 REQUEST_NOT_SUPPORTED에 실제 상태 코드를 넣어요. */
  private static ProblemDetail clientProblem(HttpStatusCode status, HttpServletRequest request) {
    ErrorCode code =
        switch (status.value()) {
          case 400 -> ErrorCode.VALIDATION_FAILED;
          case 404 -> ErrorCode.NOT_FOUND;
          case 405 -> ErrorCode.METHOD_NOT_ALLOWED;
          case 415 -> ErrorCode.UNSUPPORTED_MEDIA_TYPE;
          default -> ErrorCode.REQUEST_NOT_SUPPORTED;
        };
    ProblemDetail problem = problem(code, code.message(), request);
    problem.setStatus(status.value());
    return problem;
  }

  private void notify(String kind, String title, String detail) {
    if (alert != null) {
      alert.send(kind, title, detail);
    }
  }

  static ProblemDetail problem(ErrorCode code, String detail, HttpServletRequest request) {
    return Problems.of(code, detail, request);
  }

  /** Bean Validation 검사 이름을 대문자 스네이크로 (Min → MIN, NotNull → NOT_NULL, DecimalMax → DECIMAL_MAX). */
  static String reason(String constraint) {
    if (constraint == null || constraint.isBlank()) {
      return "INVALID";
    }
    return constraint.replaceAll("([a-z0-9])([A-Z])", "$1_$2").toUpperCase(Locale.ROOT);
  }

  private static String lastCode(String[] codes) {
    if (codes == null || codes.length == 0) {
      return null;
    }
    String code = codes[codes.length - 1];
    return code.contains(".") ? code.substring(code.lastIndexOf('.') + 1) : code;
  }
}
