package kr.mujuthaek.api.traffic.log;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/** IP 해시 비밀 값: 공개된 기본값·짧은 값은 쓰지 않아요 (2026-11-16 보안 감사 L-1). */
class IpSaltTest {

  private static final String JWT = "jwt-secret-0123456789-0123456789-0123456789";

  @Test
  void 따로_넣은_충분히_긴_값은_그대로_쓴다() {
    var resolved = IpSalt.resolve("  0123456789abcdef0123  ", JWT);
    assertThat(resolved.source()).isEqualTo(IpSalt.Source.CONFIGURED);
    assertThat(resolved.value()).isEqualTo("0123456789abcdef0123");
  }

  @Test
  void 공개된_기본값과_비거나_짧은_값은_JWT_비밀값에서_만든_값으로_바꾼다() {
    for (String weak : new String[] {null, "", "   ", "salt", IpSalt.PUBLIC_DEFAULT}) {
      var resolved = IpSalt.resolve(weak, JWT);
      assertThat(resolved.source()).isEqualTo(IpSalt.Source.DERIVED_FROM_JWT_SECRET);
      assertThat(resolved.value()).hasSize(64).doesNotContain(JWT).isNotEqualTo(weak);
    }
  }

  @Test
  void 만든_값은_같은_JWT_비밀값이면_다시_켜도_같고_비밀값이_다르면_다르다() {
    assertThat(IpSalt.resolve("", JWT).value()).isEqualTo(IpSalt.resolve(null, JWT).value());
    assertThat(IpSalt.resolve("", JWT).value()).isNotEqualTo(IpSalt.resolve("", JWT + "x").value());
  }

  @Test
  void JWT_비밀값도_없으면_켤_때마다_무작위_값을_쓴다() {
    var first = IpSalt.resolve(IpSalt.PUBLIC_DEFAULT, "");
    var second = IpSalt.resolve(IpSalt.PUBLIC_DEFAULT, null);
    assertThat(first.source()).isEqualTo(IpSalt.Source.RANDOM_PER_PROCESS);
    assertThat(first.value()).hasSize(64).isNotEqualTo(second.value());
  }
}
