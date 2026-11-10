package kr.mujuthaek.api.area.repository;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class BlankLineSkippingInputStreamTest {

  @Test
  void skipsBlankLinesOutsideQuotes() throws IOException {
    assertThat(read("a,b\n\r\n1,\"x\n\ny\"\n\n2,z\r\n\r\n", true))
        .isEqualTo("a,b\n1,\"x\n\ny\"\n2,z\r\n");
  }

  @Test
  void withoutQuoteTracking_aLoneQuoteDoesNotHideBlankLines() throws IOException {
    // | 구분 원천은 값 안에 "가 하나만 있을 수 있어요. 따옴표를 세면 그 뒤 빈 줄을 못 지워요.
    String text = "1|\"초량상로|2\r\n\r\n3|x\r\n\r\n";
    assertThat(read(text, false)).isEqualTo("1|\"초량상로|2\r\n3|x\r\n");
    assertThat(read(text, true)).contains("\r\n\r\n");
  }

  private static String read(String text, boolean trackQuotes) throws IOException {
    var in =
        new BlankLineSkippingInputStream(
            new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8)), trackQuotes);
    return new String(in.readAllBytes(), StandardCharsets.UTF_8);
  }
}
