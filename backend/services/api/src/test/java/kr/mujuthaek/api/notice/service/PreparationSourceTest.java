package kr.mujuthaek.api.notice.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class PreparationSourceTest {
  private final JsonMapper json = JsonMapper.builder().build();

  @Test
  void fingerprintIgnoresOrderingAndDisplayFlagsButRetainsMeaning() {
    var a =
        json.readTree(
            "{\"items\":[{\"id\":\"a\",\"current\":false,\"text\":\"  same   words \"},{\"id\":\"b\"}]}");
    var b =
        json.readTree(
            "{\"items\":[{\"id\":\"b\"},{\"text\":\"same words\",\"current\":true,\"id\":\"a\"}]}");
    assertThat(PreparationSource.fingerprint(a)).isEqualTo(PreparationSource.fingerprint(b));
    assertThat(PreparationSource.fingerprint(json.readTree("[\"a,b\",\"c\"]")))
        .isNotEqualTo(PreparationSource.fingerprint(json.readTree("[\"a\",\"b,c\"]")));
    assertThat(PreparationSource.fingerprint(json.readTree("{\"page\":1}")))
        .isNotEqualTo(PreparationSource.fingerprint(json.readTree("{\"page\":2}")));
  }
}
