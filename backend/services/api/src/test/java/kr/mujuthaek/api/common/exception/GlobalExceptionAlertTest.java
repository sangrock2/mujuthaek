package kr.mujuthaek.api.common.exception;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.io.IOException;
import kr.mujuthaek.api.common.alert.OpsAlert;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.async.AsyncRequestNotUsableException;

/** 운영 알림을 보내지 않아야 하는 오류 (2026-10-30 개발 서버 슬랙 알림). */
class GlobalExceptionAlertTest {

  private final OpsAlert alert = mock(OpsAlert.class);
  private final GlobalExceptionHandler handler = new GlobalExceptionHandler(alert);

  @Test
  void aClientThatLeftTheChatStreamIsNotAnError() {
    var request = new MockHttpServletRequest("GET", "/api/v1/notices/x/chat/stream");

    handler.handleDisconnected(
        new AsyncRequestNotUsableException("끊김", new IOException("Broken pipe")), request);

    verify(alert, never()).send(anyString(), anyString(), anyString());
  }

  @Test
  void ignoredCodesAreNotAlerted_otherServerErrorsAre() {
    when(alert.ignores("NOTICE_COLLECTOR_UNAVAILABLE")).thenReturn(true);
    var request = new MockHttpServletRequest("GET", "/api/admin/sources");

    handler.handle(new CustomException(ErrorCode.NOTICE_COLLECTOR_UNAVAILABLE), request);
    handler.handle(new CustomException(ErrorCode.NOTICE_REVIEW_UNAVAILABLE), request);

    verify(alert, never())
        .send(eq("api.5xx:NOTICE_COLLECTOR_UNAVAILABLE"), anyString(), anyString());
    verify(alert).send(eq("api.5xx:NOTICE_REVIEW_UNAVAILABLE"), anyString(), anyString());
  }
}
