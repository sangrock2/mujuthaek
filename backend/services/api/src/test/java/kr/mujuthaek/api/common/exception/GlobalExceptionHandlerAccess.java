package kr.mujuthaek.api.common.exception;

/** 다른 패키지의 MockMvc 테스트가 공통 오류 처리기를 붙일 때 써요 (처리기는 패키지 안에서만 보여요). */
public final class GlobalExceptionHandlerAccess {

  private GlobalExceptionHandlerAccess() {}

  public static Object handler() {
    return new GlobalExceptionHandler();
  }
}
