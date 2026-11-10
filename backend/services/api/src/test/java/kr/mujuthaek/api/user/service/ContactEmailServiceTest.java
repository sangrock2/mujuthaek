package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import kr.mujuthaek.api.common.exception.CustomException;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 이메일 모양 검사. 프론트 src/features/auth/emailFormat.ts와 같은 목록으로 맞춰 봐요 */
class ContactEmailServiceTest {

  @ParameterizedTest
  @ValueSource(
      strings = {
        "a@b.co",
        "Hong.Gil+tag@example.com",
        "홍길동@회사.한국",
        "a_b-c@sub.example.co.kr",
        "  padded@example.com  ",
        "　ideographic@example.com　", // 앞뒤 전각 공백은 지워요
      })
  void accepts(String email) {
    assertThat(ContactEmailService.normalize(email)).isEqualTo(email.strip());
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "plain",
        "a@b",
        "a@b.",
        "a@.com",
        "@example.com",
        "a@@example.com",
        "a b@example.com",
        "a　b@example.com",
        "a@exam ple.com",
        "a\u0000b@example.com",
        "a\nb@example.com",
        "a\u0085b@example.com",
      })
  void rejects(String email) {
    assertThatThrownBy(() -> ContactEmailService.normalize(email))
        .isInstanceOf(CustomException.class)
        .hasMessage("email: 이메일 주소 형식이 아니에요");
  }

  @org.junit.jupiter.api.Test
  void lengthLimits() {
    String local64 = "a".repeat(64) + "@example.com";
    assertThat(ContactEmailService.normalize(local64)).isEqualTo(local64);
    assertThatThrownBy(() -> ContactEmailService.normalize("a" + local64))
        .isInstanceOf(CustomException.class);
    String max = "a".repeat(64) + "@" + "b".repeat(185) + ".com";
    assertThat(ContactEmailService.normalize(max)).hasSize(254);
    assertThatThrownBy(() -> ContactEmailService.normalize("a" + max))
        .hasMessage("email: 254자를 넘어요");
  }

  @org.junit.jupiter.api.Test
  void lowercasesOnlyTheDomain() {
    assertThat(ContactEmailService.normalize("Hong.Gil@Example.COM"))
        .isEqualTo("Hong.Gil@example.com");
  }
}
