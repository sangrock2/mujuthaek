package kr.mujuthaek.api.area.repository;

import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * 따옴표 밖의 빈 줄(\n 또는 \r\n만 있는 줄)을 건너뛰어요. 공공데이터 파일 끝에 붙은 빈 줄 때문에 COPY가 실패하지 않게요.
 *
 * <p>바이트 단위로 보지만 안전해요: CP949의 둘째 바이트(0x41 이상)와 UTF-8의 이어지는 바이트(0x80 이상)는 따옴표(0x22)나 줄바꿈(0x0A,
 * 0x0D)이 될 수 없어요.
 */
final class BlankLineSkippingInputStream extends FilterInputStream {

  private final boolean trackQuotes;
  private boolean atLineStart = true;
  private boolean inQuotes = false;
  private int pending = -1;

  BlankLineSkippingInputStream(InputStream in) {
    this(in, true);
  }

  /** trackQuotes가 false면 따옴표를 신경 쓰지 않아요 (| 구분처럼 값을 따옴표로 감싸지 않아서, 값 안의 "가 그대로 있는 파일). */
  BlankLineSkippingInputStream(InputStream in, boolean trackQuotes) {
    super(in);
    this.trackQuotes = trackQuotes;
  }

  @Override
  public int read() throws IOException {
    while (true) {
      int b;
      if (pending != -1) {
        b = pending;
        pending = -1;
      } else {
        b = super.read();
      }
      if (b == -1) {
        return -1;
      }
      if (!inQuotes && atLineStart) {
        if (b == '\n') {
          continue;
        }
        if (b == '\r') {
          int next = super.read();
          if (next == '\n' || next == -1) {
            continue;
          }
          pending = next;
          atLineStart = false;
          return b;
        }
      }
      if (trackQuotes && b == '"') {
        inQuotes = !inQuotes;
      }
      atLineStart = !inQuotes && b == '\n';
      return b;
    }
  }

  @Override
  public int read(byte[] buf, int off, int len) throws IOException {
    if (len == 0) {
      return 0;
    }
    int n = 0;
    while (n < len) {
      int b = read();
      if (b == -1) {
        return n == 0 ? -1 : n;
      }
      buf[off + n++] = (byte) b;
    }
    return n;
  }

  @Override
  public long skip(long n) throws IOException {
    long skipped = 0;
    while (skipped < n && read() != -1) {
      skipped++;
    }
    return skipped;
  }

  @Override
  public int available() {
    return 0;
  }

  @Override
  public boolean markSupported() {
    return false;
  }
}
