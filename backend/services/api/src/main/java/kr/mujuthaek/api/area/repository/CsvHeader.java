package kr.mujuthaek.api.area.repository;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.List;

/** 원천 CSV의 머리줄. 나머지 줄은 그대로 COPY에 넘겨야 해서, 머리줄만 바이트로 읽어 칸 이름 목록으로 바꿔요. */
final class CsvHeader {

  private CsvHeader() {}

  /** 첫 줄을 줄바꿈까지만 읽어요. 앞의 BOM과 끝의 \r은 빼요. 파일이 비었으면 실패해요. */
  static List<String> read(BufferedInputStream in, Charset charset) throws IOException {
    ByteArrayOutputStream line = new ByteArrayOutputStream();
    int b;
    while ((b = in.read()) != -1 && b != '\n') {
      line.write(b);
    }
    if (line.size() == 0 && b == -1) {
      throw new AreaLoadException("파일이 비어 있어요");
    }
    String text = line.toString(charset);
    if (text.startsWith("﻿")) {
      text = text.substring(1);
    }
    if (text.endsWith("\r")) {
      text = text.substring(0, text.length() - 1);
    }
    return parse(text);
  }

  /** 머리줄 한 줄을 칸 이름 목록으로. 따옴표로 감싼 칸("예술, 스포츠")과 따옴표 두 개("")를 처리해요. */
  static List<String> parse(String line) {
    List<String> out = new ArrayList<>();
    StringBuilder cell = new StringBuilder();
    boolean quoted = false;
    for (int i = 0; i < line.length(); i++) {
      char ch = line.charAt(i);
      if (quoted) {
        if (ch == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') {
          cell.append('"');
          i++;
        } else if (ch == '"') {
          quoted = false;
        } else {
          cell.append(ch);
        }
      } else if (ch == '"') {
        quoted = true;
      } else if (ch == ',') {
        out.add(cell.toString().trim());
        cell.setLength(0);
      } else {
        cell.append(ch);
      }
    }
    out.add(cell.toString().trim());
    return out;
  }
}
