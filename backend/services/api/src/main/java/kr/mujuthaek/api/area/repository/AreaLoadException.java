package kr.mujuthaek.api.area.repository;

/** 적재를 멈춰야 하는 문제 (칸 없음, 파일이 비었음, 행이 크게 줄었음 등). 메시지는 load_runs.error에 남아요. */
public class AreaLoadException extends RuntimeException {

  public AreaLoadException(String message) {
    super(message);
  }

  public AreaLoadException(String message, Throwable cause) {
    super(message, cause);
  }
}
