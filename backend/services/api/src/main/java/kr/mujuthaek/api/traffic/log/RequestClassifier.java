package kr.mujuthaek.api.traffic.log;

import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

/** 요청 한 건을 분류하는 규칙(스프링 없음): 누가 보냈는지(사람·봇·도구), 어느 영역인지, 로그인 결과, 경로 정리, IP 가리기. */
public final class RequestClassifier {

  /** 요청을 보낸 쪽. */
  public enum Client {
    HUMAN,
    SEARCH_BOT,
    PREVIEW_BOT,
    TOOL,
    MONITOR,
    UNKNOWN
  }

  /** 요청 영역. */
  public enum Area {
    API,
    ADMIN,
    AUTH,
    LOGIN,
    /** 프론트 서버가 넘긴 화면 요청(주소를 직접 연 것). 응답 코드·처리 시간은 몰라요 */
    PAGE
  }

  /** 소셜 로그인이 끝났을 때의 결과(돌아가는 주소로 판단). */
  public enum LoginResult {
    SIGNUP,
    LOGIN,
    FAILED
  }

  // 검색엔진: 구글·네이버(Yeti)·빙·다음·애플·야후·덕덕고·바이두·얀덱스
  private static final List<String> SEARCH =
      List.of(
          "googlebot",
          "google-inspectiontool",
          "yeti",
          "bingbot",
          "daumoa",
          "applebot",
          "slurp",
          "duckduckbot",
          "baiduspider",
          "yandex");
  // 링크 미리보기: 카카오톡·페이스북·트위터·슬랙·디스코드·텔레그램·라인·링크드인
  private static final List<String> PREVIEW =
      List.of(
          "kakaotalk-scrap",
          "facebookexternalhit",
          "twitterbot",
          "slackbot",
          "discordbot",
          "telegrambot",
          "line/",
          "linkedinbot");
  private static final List<String> MONITOR =
      List.of("uptimerobot", "pingdom", "statuscake", "datadog", "elb-healthchecker", "kube-probe");
  // 사람이 브라우저로 보내지 않는 도구·자동화
  private static final List<String> TOOL =
      List.of(
          "curl/",
          "wget/",
          "python-requests",
          "python-urllib",
          "aiohttp",
          "httpx",
          "go-http-client",
          "okhttp",
          "java/",
          "apache-httpclient",
          "axios/",
          "node-fetch",
          "undici",
          "postmanruntime",
          "insomnia",
          "headlesschrome",
          "phantomjs",
          "playwright",
          "puppeteer",
          "selenium",
          "scrapy",
          "httpclient");
  private static final Pattern GENERIC_BOT = Pattern.compile("bot\\b|crawler|spider|crawl");
  private static final Pattern UUID =
      Pattern.compile(
          "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
  private static final Pattern NUMBER = Pattern.compile("/\\d+(?=/|$)");

  private RequestClassifier() {}

  /** User-Agent → 보낸 쪽. 비어 있으면 UNKNOWN(대개 자동화). 브라우저처럼 보여도 headless·자동화 표시가 있으면 TOOL. */
  public static Client client(String userAgent) {
    if (userAgent == null || userAgent.isBlank()) {
      return Client.UNKNOWN;
    }
    String ua = userAgent.toLowerCase(Locale.ROOT);
    if (contains(ua, SEARCH)) return Client.SEARCH_BOT;
    if (contains(ua, PREVIEW)) return Client.PREVIEW_BOT;
    if (contains(ua, MONITOR)) return Client.MONITOR;
    if (contains(ua, TOOL)) return Client.TOOL;
    if (GENERIC_BOT.matcher(ua).find()) return Client.SEARCH_BOT;
    return ua.startsWith("mozilla/") ? Client.HUMAN : Client.UNKNOWN;
  }

  /** 경로 → 영역. 소셜 로그인 돌아오는 곳은 LOGIN, 토큰 재발급·로그아웃은 AUTH. */
  public static Area area(String path) {
    if (path.startsWith("/api/admin/")) return Area.ADMIN;
    if (path.startsWith("/login/oauth2/")) return Area.LOGIN;
    if (path.startsWith("/api/auth/") || path.startsWith("/oauth2/")) return Area.AUTH;
    return Area.API;
  }

  /**
   * 소셜 로그인이 끝나 프론트로 돌려보내는 주소 → 결과. 처음 가입은 {@code /auth/callback?new=1}, 로그인은 {@code
   * /auth/callback}, 실패는 {@code /login?error=}이에요(user 모듈 LoginSuccessHandler·LoginFailureHandler).
   * 탈퇴 재인증 등 다른 곳은 null.
   */
  public static LoginResult loginResult(String path, String location) {
    if (location == null || !path.startsWith("/login/oauth2/")) {
      return null;
    }
    if (location.contains("/login?error=")) return LoginResult.FAILED;
    if (location.contains("/auth/callback")) {
      return location.contains("new=1") ? LoginResult.SIGNUP : LoginResult.LOGIN;
    }
    return null;
  }

  /** 경로의 ID(UUID·숫자)를 {id}로 바꿔 같은 화면 요청을 한 줄로 셉니다. 쿼리는 버려요(값에 개인 정보가 올 수 있음). */
  public static String normalizePath(String path) {
    String p = UUID.matcher(path).replaceAll("{id}");
    p = NUMBER.matcher(p).replaceAll("/{id}");
    return p.length() > 200 ? p.substring(0, 200) : p;
  }

  /** 화면에 보여 줄 가린 IP: IPv4는 마지막 자리(a.b.c.x), IPv6는 앞 3묶음만. */
  public static String maskIp(String ip) {
    if (ip == null || ip.isBlank()) return null;
    if (ip.contains(":")) {
      String[] parts = ip.split(":");
      return String.join(":", java.util.Arrays.copyOf(parts, Math.min(3, parts.length))) + ":…";
    }
    int last = ip.lastIndexOf('.');
    return last < 0 ? ip : ip.substring(0, last) + ".x";
  }

  private static boolean contains(String ua, List<String> words) {
    for (String w : words) {
      if (ua.contains(w)) return true;
    }
    return false;
  }
}
