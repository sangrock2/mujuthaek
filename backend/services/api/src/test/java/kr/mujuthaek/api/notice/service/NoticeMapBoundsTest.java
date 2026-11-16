package kr.mujuthaek.api.notice.service;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.junit.jupiter.api.Test;

/**
 * 지도 범위: NaN·무한대·범위 밖 좌표는 DB에 가기 전에 400이에요 (2026-11-16 보안 감사 L-12). 검사는 DB를 쓰기 전에 끝나서 의존성 없이 만들어요.
 */
class NoticeMapBoundsTest {

  private final NoticeQueryService service =
      new NoticeQueryService(null, null, null, null, null, null, null);

  @Test
  void 숫자가_아니거나_범위를_벗어난_좌표는_400() {
    double[][] bad = {
      {Double.NaN, 126.9, 37.6, 127.1},
      {37.4, Double.NEGATIVE_INFINITY, 37.6, 127.1},
      {37.4, 126.9, Double.POSITIVE_INFINITY, 127.1},
      {37.4, 126.9, 37.6, Double.NaN},
      {-91, 126.9, 37.6, 127.1},
      {37.4, 126.9, 90.5, 127.1},
      {37.4, -180.5, 37.6, 127.1},
      {37.4, 126.9, 37.6, 181},
      {37.6, 126.9, 37.4, 127.1}, // 남서쪽이 북동쪽보다 커요
    };
    for (double[] b : bad) {
      assertThatThrownBy(
              () ->
                  service.map(
                      b[0], b[1], b[2], b[3], 12, null, List.of(), List.of(), List.of(), 10))
          .isInstanceOfSatisfying(
              CustomException.class,
              e ->
                  org.assertj.core.api.Assertions.assertThat(e.errorCode())
                      .isEqualTo(ErrorCode.VALIDATION_FAILED));
    }
  }
}
