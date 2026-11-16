package kr.mujuthaek.api.common.text;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 수집·추출한 외부 링크(신청·원문·안내 주소) 검사. http·https 절대 주소이고 호스트가 있고, 사용자 정보(user:pass@)·공백·제어 문자가 없을 때만 그대로
 * 쓰고, 아니면 null이에요(화면이 링크를 숨겨요).
 *
 * <p>예전에는 혜택의 신청·원문 링크와 공고 안내 링크가 수집부터 화면까지 한 번도 스킴·호스트 검사를 받지 않아서, 기관 기록이 조작되면 {@code data:}·
 * {@code search-ms:}·{@code intent:} 같은 링크가 「신청하러 가기」 버튼이 될 수 있었어요(2026-11-16 보안 감사 L-4). 받을 때와 내보낼
 * 때 모두 써요.
 */
public final class ExternalUrl {

  static final int MAX_LENGTH = 2048;

  /** 계약(contracts/events)의 링크 칸 길이 상한 */
  static final int CONTRACT_MAX_LENGTH = 2000;

  private static final Logger log = LoggerFactory.getLogger(ExternalUrl.class);

  private ExternalUrl() {}

  /**
   * 들어온 이벤트에서 계약의 링크 모양(http·https, 호스트, @·빈칸·역슬래시 없음)이 아닌 칸을 null로 비워요. 계약 검사 전에 불러요.
   *
   * <p>계약은 보내는 쪽(추출 서비스)이 지켜요. 그런데 배포 순서에 따라 이 서버가 먼저 새 계약으로 바뀌면, 예전 추출 서비스가 보낸 이벤트(scheme 없는 주소
   * 등)가 링크 하나 때문에 통째로 실패 큐로 가고 다시 넣어도 계속 거절돼요. 선택 칸인 링크만 비우고 나머지 공고·혜택 내용은 받아요(보안 감사 L-4).
   *
   * @param pointers 비울 수 있는 칸의 JSON Pointer (예: /payload/source/detailUrl)
   * @return 비운 칸 수
   */
  public static int clearOffContract(JsonNode root, String... pointers) {
    int cleared = 0;
    for (String pointer : pointers) {
      int slash = pointer.lastIndexOf('/');
      JsonNode parent = slash <= 0 ? root : root.at(pointer.substring(0, slash));
      String field = pointer.substring(slash + 1);
      if (!(parent instanceof ObjectNode object)) {
        continue;
      }
      JsonNode value = object.get(field);
      if (value == null || value.isNull()) {
        continue;
      }
      String text = value.isString() ? value.asString() : null;
      if (text == null
          || text.length() > CONTRACT_MAX_LENGTH
          || !CONTRACT_LINK.matcher(text).matches()) {
        object.putNull(field);
        cleared++;
        log.warn("계약 모양이 아닌 링크를 비웠어요: {}", pointer);
      }
    }
    return cleared;
  }

  /** contracts/events의 publicLink 패턴과 같아요 */
  private static final Pattern CONTRACT_LINK =
      Pattern.compile("^https?://[^\\s/?#@\\\\]+(?:[/?#]\\S*)?$");

  /** 쓸 수 있는 링크면 앞뒤 공백을 뺀 값, 아니면 null */
  public static String safe(String value) {
    if (value == null) {
      return null;
    }
    String url = value.strip();
    if (url.isEmpty() || url.length() > MAX_LENGTH) {
      return null;
    }
    for (int i = 0; i < url.length(); i++) {
      char c = url.charAt(i);
      if (Character.isWhitespace(c) || Character.isISOControl(c) || Character.isSpaceChar(c)) {
        return null;
      }
    }
    try {
      URI uri = new URI(url);
      String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
      if (!scheme.equals("http") && !scheme.equals("https")) {
        return null;
      }
      if (uri.getRawUserInfo() != null || uri.getHost() == null || uri.getHost().isBlank()) {
        return null;
      }
      return url;
    } catch (URISyntaxException e) {
      return null;
    }
  }
}
