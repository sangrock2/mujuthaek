package kr.mujuthaek.api.notice.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/** 공개 정보만 담는 준비용 snapshot. 순서·공백·표시 시각에 의한 변경을 제외한다. */
public record PreparationSource(
    UUID noticeId, String field, int version, String revision, JsonNode content) {
  public static String fingerprint(JsonNode node) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256")
                  .digest(canonical(node).getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }

  private static String canonical(JsonNode node) {
    if (node.isObject()) {
      var fields = new ArrayList<>(node.properties());
      fields.sort(java.util.Map.Entry.comparingByKey());
      return fields.stream()
          .filter(e -> !e.getKey().equals("current"))
          .map(e -> e.getKey().length() + ":" + e.getKey() + "=" + canonical(e.getValue()))
          .collect(java.util.stream.Collectors.joining(",", "{", "}"));
    }
    if (node.isArray()) {
      var values = new ArrayList<String>();
      node.forEach(n -> values.add(canonical(n)));
      values.sort(Comparator.naturalOrder());
      return String.join(",", values).transform(s -> "[" + s + "]");
    }
    return node.isString()
        ? tools.jackson.databind.node.JsonNodeFactory.instance
            .stringNode(node.asString().strip().replaceAll("\\s+", " "))
            .toString()
        : node.toString();
  }
}
