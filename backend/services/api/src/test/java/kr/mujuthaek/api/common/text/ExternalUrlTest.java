package kr.mujuthaek.api.common.text;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 외부 링크는 http·https 절대 주소만 (2026-11-16 보안 감사 L-4). */
class ExternalUrlTest {

  @ParameterizedTest
  @ValueSource(
      strings = {
        "https://www.gov.kr/portal/service/serviceInfo/123",
        "http://youth.seoul.go.kr/apply?id=1&x=%20",
        "HTTPS://EXAMPLE.GO.KR/a",
        "  https://example.go.kr/trimmed  "
      })
  void keepsWebLinks(String url) {
    assertThat(ExternalUrl.safe(url)).isEqualTo(url.strip());
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "search-ms:query=x",
        "ms-word:ofe|u|https://evil.example/a.docx",
        "intent://scan/#Intent;scheme=zxing;end",
        "file:///C:/Windows/win.ini",
        "//evil.example/path",
        "/relative/path",
        "https://user:pass@evil.example/",
        "https://evil.example/a b",
        "https://evil.example/\u0000",
        "https:///nohost",
        "",
        "   "
      })
  void dropsEverythingElse(String url) {
    assertThat(ExternalUrl.safe(url)).isNull();
  }

  @org.junit.jupiter.api.Test
  void nullAndOverlongAreDropped() {
    assertThat(ExternalUrl.safe(null)).isNull();
    assertThat(ExternalUrl.safe("https://example.go.kr/" + "a".repeat(ExternalUrl.MAX_LENGTH)))
        .isNull();
  }

  /** 예전 추출 서비스가 보낸 이벤트도 링크 칸만 비우고 받아요 (계약 검사 전에) */
  @org.junit.jupiter.api.Test
  void offContractLinksAreClearedBeforeValidation() {
    var json = tools.jackson.databind.json.JsonMapper.builder().build();
    var event =
        json.readTree(
            """
            {"payload":{"source":{"detailUrl":"www.youth.go.kr/a","applyUrl":"https://www.gov.kr/x"},
             "policyInfo":{"applyUrl":"HTTPS://EXAMPLE.GO.KR","guideUrl":null},"detailUrl":"https://user@evil.example/"}}
            """);

    int cleared =
        ExternalUrl.clearOffContract(
            event,
            "/payload/source/detailUrl",
            "/payload/source/applyUrl",
            "/payload/policyInfo/applyUrl",
            "/payload/policyInfo/guideUrl",
            "/payload/detailUrl",
            "/payload/missing/detailUrl");

    assertThat(cleared).isEqualTo(3);
    assertThat(event.at("/payload/source/detailUrl").isNull()).isTrue();
    assertThat(event.at("/payload/source/applyUrl").asString()).isEqualTo("https://www.gov.kr/x");
    assertThat(event.at("/payload/policyInfo/applyUrl").isNull()).isTrue();
    assertThat(event.at("/payload/policyInfo/guideUrl").isNull()).isTrue();
    assertThat(event.at("/payload/detailUrl").isNull()).isTrue();
  }
}
