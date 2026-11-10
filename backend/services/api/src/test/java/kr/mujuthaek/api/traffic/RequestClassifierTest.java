package kr.mujuthaek.api.traffic;

import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.traffic.log.RequestClassifier;
import kr.mujuthaek.api.traffic.log.RequestClassifier.Area;
import kr.mujuthaek.api.traffic.log.RequestClassifier.Client;
import kr.mujuthaek.api.traffic.log.RequestClassifier.LoginResult;
import org.junit.jupiter.api.Test;

class RequestClassifierTest {

  @Test
  void 보낸_쪽을_나눈다() {
    assertThat(
            RequestClassifier.client(
                "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"))
        .isEqualTo(Client.HUMAN);
    assertThat(
            RequestClassifier.client(
                "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"))
        .isEqualTo(Client.SEARCH_BOT);
    assertThat(
            RequestClassifier.client("Mozilla/5.0 (compatible; Yeti/1.1; +https://naver.me/spd)"))
        .isEqualTo(Client.SEARCH_BOT);
    assertThat(RequestClassifier.client("facebookexternalhit/1.1 kakaotalk-scrap/1.0"))
        .isEqualTo(Client.PREVIEW_BOT);
    assertThat(RequestClassifier.client("curl/8.4.0")).isEqualTo(Client.TOOL);
    assertThat(RequestClassifier.client("python-requests/2.32")).isEqualTo(Client.TOOL);
    assertThat(RequestClassifier.client("Mozilla/5.0 HeadlessChrome/120.0")).isEqualTo(Client.TOOL);
    assertThat(RequestClassifier.client("Mozilla/5.0+(compatible; UptimeRobot/2.0)"))
        .isEqualTo(Client.MONITOR);
    assertThat(RequestClassifier.client("")).isEqualTo(Client.UNKNOWN);
    assertThat(RequestClassifier.client("SomethingCrawler/1.0")).isEqualTo(Client.SEARCH_BOT);
  }

  @Test
  void 소셜_로그인_결과는_돌려보내는_주소로_안다() {
    String callback = "/login/oauth2/code/kakao";
    assertThat(RequestClassifier.loginResult(callback, "http://localhost:3000/auth/callback?new=1"))
        .isEqualTo(LoginResult.SIGNUP);
    assertThat(RequestClassifier.loginResult(callback, "http://localhost:3000/auth/callback"))
        .isEqualTo(LoginResult.LOGIN);
    assertThat(
            RequestClassifier.loginResult(
                callback, "http://localhost:3000/login?error=social&reason=access_denied"))
        .isEqualTo(LoginResult.FAILED);
    assertThat(
            RequestClassifier.loginResult(callback, "http://localhost:3000/mypage?withdraw=done"))
        .isNull();
    assertThat(RequestClassifier.loginResult("/api/v1/notices", "http://x/auth/callback?new=1"))
        .isNull();
  }

  @Test
  void 영역_경로_IP를_정리한다() {
    assertThat(RequestClassifier.area("/api/admin/reviews")).isEqualTo(Area.ADMIN);
    assertThat(RequestClassifier.area("/login/oauth2/code/kakao")).isEqualTo(Area.LOGIN);
    assertThat(RequestClassifier.area("/api/auth/refresh")).isEqualTo(Area.AUTH);
    assertThat(RequestClassifier.area("/api/v1/notices")).isEqualTo(Area.API);
    assertThat(
            RequestClassifier.normalizePath(
                "/api/v1/notices/01a1723f-ee21-7000-a557-7365aad3daa7/units/12"))
        .isEqualTo("/api/v1/notices/{id}/units/{id}");
    assertThat(RequestClassifier.maskIp("203.0.113.45")).isEqualTo("203.0.113.x");
    assertThat(RequestClassifier.maskIp("2001:db8:85a3:0:0:8a2e:370:7334"))
        .isEqualTo("2001:db8:85a3:…");
    assertThat(RequestClassifier.maskIp(null)).isNull();
  }
}
