package kr.mujuthaek.api.area.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import kr.mujuthaek.api.area.domain.AreaSource;
import org.junit.jupiter.api.Test;

/** 머리줄 읽기와 빈 줄 건너뛰기. */
class CsvReadingTest {

  @Test
  void parsesQuotedHeaderCells() {
    assertThat(CsvHeader.parse("\"상가업소번호\",\"상호명\",\"예술, 스포츠\",\"따옴표\"\"칸\""))
        .containsExactly("상가업소번호", "상호명", "예술, 스포츠", "따옴표\"칸");
    assertThat(CsvHeader.parse("정류장번호, 정류장명 ,위도")).containsExactly("정류장번호", "정류장명", "위도");
  }

  @Test
  void readsOnlyTheHeaderLineAndLeavesTheRestForCopy() throws IOException {
    var in = buffered("﻿역번호,역사명\r\n150,서울역\n", StandardCharsets.UTF_8);
    assertThat(CsvHeader.read(in, StandardCharsets.UTF_8)).containsExactly("역번호", "역사명");
    assertThat(new String(in.readAllBytes(), StandardCharsets.UTF_8)).isEqualTo("150,서울역\n");
  }

  @Test
  void readsCp949Header() throws IOException {
    Charset cp949 = AreaSource.Charsets.CP949;
    assertThat(CsvHeader.read(buffered("정류장번호,정류장명\n", cp949), cp949))
        .containsExactly("정류장번호", "정류장명");
  }

  @Test
  void emptyFileFails() {
    assertThatThrownBy(
            () -> CsvHeader.read(buffered("", StandardCharsets.UTF_8), StandardCharsets.UTF_8))
        .isInstanceOf(AreaLoadException.class)
        .hasMessageContaining("비어");
  }

  @Test
  void skipsBlankLinesOutsideQuotes() throws IOException {
    assertThat(skipBlank("a,b\n\n\r\nc,d\n\n")).isEqualTo("a,b\nc,d\n");
  }

  @Test
  void keepsLineBreaksInsideQuotedCells() throws IOException {
    assertThat(skipBlank("a,\"첫 줄\n\n둘째 줄\"\n\nb\n")).isEqualTo("a,\"첫 줄\n\n둘째 줄\"\nb\n");
  }

  private static BufferedInputStream buffered(String text, Charset charset) {
    return new BufferedInputStream(new ByteArrayInputStream(text.getBytes(charset)));
  }

  private static String skipBlank(String text) throws IOException {
    try (InputStream in =
        new BlankLineSkippingInputStream(
            new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8)))) {
      return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    }
  }
}
