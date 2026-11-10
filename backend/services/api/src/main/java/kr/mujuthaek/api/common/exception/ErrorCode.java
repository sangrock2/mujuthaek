package kr.mujuthaek.api.common.exception;

import java.util.Locale;
import org.springframework.http.HttpStatus;

/**
 * 우리 오류 코드. 응답의 {@code code}에 그대로 나가고 화면이 이걸로 문구를 골라요. 모듈마다 필요한 코드를 여기에 추가해요 (접두어로 모듈 구분, 예:
 * NOTICE_NOT_FOUND).
 */
public enum ErrorCode {
  VALIDATION_FAILED(HttpStatus.BAD_REQUEST, "입력값이 올바르지 않아요"),
  INVALID_CURSOR(HttpStatus.BAD_REQUEST, "목록 위치(cursor)가 올바르지 않아요. 처음부터 다시 받아 주세요"),
  UNAUTHENTICATED(HttpStatus.UNAUTHORIZED, "로그인이 필요해요"),
  FORBIDDEN(HttpStatus.FORBIDDEN, "권한이 없어요"),
  CSRF_INVALID(HttpStatus.FORBIDDEN, "요청 확인 값(CSRF)이 없거나 달라요"),
  NOT_FOUND(HttpStatus.NOT_FOUND, "대상을 찾을 수 없어요"),
  METHOD_NOT_ALLOWED(HttpStatus.METHOD_NOT_ALLOWED, "이 주소에서 지원하지 않는 요청 방식이에요"),
  UNSUPPORTED_MEDIA_TYPE(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "지원하지 않는 요청 본문 형식이에요"),
  /** 위 코드에 없는 그 밖의 4xx 표준 오류 (예: 406). 응답 status는 실제 상태 코드예요. */
  REQUEST_NOT_SUPPORTED(HttpStatus.BAD_REQUEST, "처리할 수 없는 요청이에요"),
  CONFLICT(HttpStatus.CONFLICT, "이미 처리된 요청과 겹쳐요"),
  RATE_LIMITED(HttpStatus.TOO_MANY_REQUESTS, "요청이 너무 잦아요. 잠시 뒤에 다시 해 주세요"),
  INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "서버 오류가 났어요"),

  // notice
  NOTICE_NOT_FOUND(HttpStatus.NOT_FOUND, "공고를 찾을 수 없어요"),
  NOTICE_COLLECTOR_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "수집기에 연결하지 못했어요. 잠시 뒤에 다시 해 주세요"),
  NOTICE_REPORT_NOT_FOUND(HttpStatus.NOT_FOUND, "제보를 찾을 수 없어요"),
  NOTICE_REVIEW_NOT_FOUND(HttpStatus.NOT_FOUND, "검수 항목을 찾을 수 없어요"),
  NOTICE_REVIEW_CONFLICT(HttpStatus.CONFLICT, "이미 처리됐거나 새 버전으로 바뀐 검수 항목이에요"),
  NOTICE_REVIEW_INVALID(HttpStatus.UNPROCESSABLE_CONTENT, "검수 결과가 공고 형식에 맞지 않아요"),
  NOTICE_REVIEW_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "검수 서버에 연결하지 못했어요. 잠시 뒤에 다시 해 주세요"),

  // benefit
  BENEFIT_NOT_FOUND(HttpStatus.NOT_FOUND, "혜택을 찾을 수 없어요"),

  // area
  AREA_SITE_NOT_FOUND(HttpStatus.NOT_FOUND, "위치를 찾을 수 없어요 (좌표를 아직 못 찾은 위치 포함)"),

  // user
  UNSUPPORTED_SOCIAL_PROVIDER(HttpStatus.BAD_REQUEST, "지원하지 않는 소셜 로그인이에요"),
  INVALID_REFRESH_TOKEN(HttpStatus.UNAUTHORIZED, "로그인이 만료됐어요. 다시 로그인해 주세요"),
  WITHDRAWAL_PROVIDER_NOT_LINKED(HttpStatus.BAD_REQUEST, "연결되지 않은 소셜 계정이에요"),
  WITHDRAWAL_TICKET_INVALID(HttpStatus.BAD_REQUEST, "탈퇴 요청이 만료됐어요. 다시 시도해 주세요"),
  WITHDRAWAL_ACCOUNT_MISMATCH(HttpStatus.BAD_REQUEST, "탈퇴하려는 계정과 다시 로그인한 계정이 달라요"),
  FAVORITE_TARGET_NOT_FOUND(HttpStatus.NOT_FOUND, "관심으로 저장할 공고·정책을 찾을 수 없어요"),
  FAVORITE_LIMIT_EXCEEDED(HttpStatus.CONFLICT, "관심 공고는 200개까지 저장할 수 있어요"),
  EMAIL_ALREADY_USED(HttpStatus.CONFLICT, "이미 다른 계정에서 쓰고 있는 이메일이에요"),
  ACCOUNT_SUSPENDED(HttpStatus.FORBIDDEN, "이용이 정지된 계정이에요"),

  // notification
  PUSH_NOT_CONFIGURED(HttpStatus.SERVICE_UNAVAILABLE, "웹 푸시 알림을 아직 쓸 수 없어요"),
  PUSH_SUBSCRIPTION_NOT_FOUND(HttpStatus.NOT_FOUND, "등록된 기기를 찾을 수 없어요"),
  NOTIFICATION_NOT_FOUND(HttpStatus.NOT_FOUND, "알림을 찾을 수 없어요"),

  // eligibility
  CRITERIA_NOT_FOUND(HttpStatus.NOT_FOUND, "그 연도의 판정 기준값이 아직 없어요"),
  ELIGIBILITY_FIELD_MISMATCH(HttpStatus.BAD_REQUEST, "판정하려는 분야와 판정 틀의 분야(schema)가 달라요"),
  ELIGIBILITY_INVALID_FRAME(HttpStatus.BAD_REQUEST, "판정 틀 형식이 올바르지 않아요"),

  // chat
  CHAT_MESSAGE_NOT_FOUND(HttpStatus.NOT_FOUND, "메시지를 찾을 수 없어요"),
  CHAT_INVALID_CONTENT(HttpStatus.BAD_REQUEST, "메시지는 1~500자로 써 주세요"),
  CHAT_PERSONAL_INFO(HttpStatus.BAD_REQUEST, "휴대폰 번호·주민등록번호는 채팅에 올릴 수 없어요"),
  CHAT_REPLY_DEPTH(HttpStatus.BAD_REQUEST, "답장에는 답장할 수 없어요"),
  CHAT_NOT_OWNER(HttpStatus.FORBIDDEN, "내가 쓴 메시지만 지울 수 있어요"),
  CHAT_READ_ONLY(HttpStatus.CONFLICT, "접수 마감 30일이 지나 읽기만 할 수 있는 채팅방이에요"),
  CHAT_ALREADY_REPORTED(HttpStatus.CONFLICT, "이미 신고한 메시지예요"),
  CHAT_RATE_LIMITED(HttpStatus.TOO_MANY_REQUESTS, "메시지는 1분에 5개까지 보낼 수 있어요"),
  ;

  private static final String TYPE_BASE = "https://mujuthaek.kr/problems/";

  private final HttpStatus status;
  private final String message;

  ErrorCode(HttpStatus status, String message) {
    this.status = status;
    this.message = message;
  }

  public HttpStatus status() {
    return status;
  }

  /** 응답의 title. */
  public String message() {
    return message;
  }

  /** 응답의 type. 예: VALIDATION_FAILED → https://mujuthaek.kr/problems/validation-failed */
  public String type() {
    return TYPE_BASE + name().toLowerCase(Locale.ROOT).replace('_', '-');
  }
}
