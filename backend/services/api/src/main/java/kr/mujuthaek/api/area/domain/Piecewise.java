package kr.mujuthaek.api.area.domain;

import java.math.BigDecimal;
import java.math.MathContext;
import java.util.Arrays;
import java.util.List;

/**
 * 점수 규칙 하나: 점(xs, ys)을 직선으로 잇고, 양끝 밖은 끝 값. DB 함수 {@code area.piecewise}와 같은 계산이에요.
 *
 * <p>요청 때 계산하는 점수(직장 거리 등)에 써요. 저장하는 점수는 SQL이 계산해요.
 */
public record Piecewise(List<BigDecimal> xs, List<BigDecimal> ys) {

  public Piecewise {
    xs = List.copyOf(xs);
    ys = List.copyOf(ys);
    if (xs.size() != ys.size() || xs.size() < 2) {
      throw new IllegalArgumentException("점은 두 개 이상, xs와 ys 개수가 같아야 해요");
    }
    for (int i = 1; i < xs.size(); i++) {
      if (xs.get(i).compareTo(xs.get(i - 1)) <= 0) {
        throw new IllegalArgumentException("xs는 오름차순이어야 해요");
      }
    }
  }

  public static Piecewise of(long[] xs, long[] ys) {
    return new Piecewise(decimals(xs), decimals(ys));
  }

  public BigDecimal apply(BigDecimal x) {
    int n = xs.size();
    if (x.compareTo(xs.get(0)) <= 0) {
      return ys.get(0);
    }
    if (x.compareTo(xs.get(n - 1)) >= 0) {
      return ys.get(n - 1);
    }
    for (int i = 1; i < n; i++) {
      if (x.compareTo(xs.get(i)) <= 0) {
        BigDecimal x0 = xs.get(i - 1);
        BigDecimal y0 = ys.get(i - 1);
        return y0.add(
            ys.get(i)
                .subtract(y0)
                .multiply(x.subtract(x0))
                .divide(xs.get(i).subtract(x0), MathContext.DECIMAL128));
      }
    }
    return ys.get(n - 1);
  }

  private static List<BigDecimal> decimals(long[] values) {
    return Arrays.stream(values).mapToObj(BigDecimal::valueOf).toList();
  }
}
