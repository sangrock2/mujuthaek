package kr.mujuthaek.api.common.exception;

import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import org.springframework.http.ProblemDetail;

/**
 * 오류 응답(Problem Details) 만들기. 컨트롤러 오류(GlobalExceptionHandler)와 보안 필터의 401·403(user 모듈)이 같은 모양으로 나가게
 * 한 곳에서 만들어요.
 */
public final class Problems {

  private Problems() {}

  public static ProblemDetail of(ErrorCode code, String detail, HttpServletRequest request) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(code.status(), detail);
    problem.setType(URI.create(code.type()));
    problem.setTitle(code.message());
    problem.setInstance(URI.create(request.getRequestURI()));
    problem.setProperty("code", code.name());
    return problem;
  }
}
