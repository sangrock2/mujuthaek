package kr.mujuthaek.api.common.text;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 휴대폰 번호·주민등록번호는 잡고, 공고에 자주 나오는 다른 숫자는 놓아줘요. */
class PersonalInfoTest {

  @ParameterizedTest
  @ValueSource(
      strings = {
        "010-1234-5678",
        "연락은 01012345678로",
        "010 1234 5678",
        "010.1234.5678",
        "011-123-4567",
        "970101-1234567",
        "9701011234567",
        "주민번호 970101 - 2234567 입니다",
        "외국인 000315-5123456"
      })
  void catchesMobileAndResidentNumbers(String text) {
    assertThat(PersonalInfo.contains(text)).isTrue();
  }

  /** 예전 검사를 지나가던 모양 (2026-11-16 보안 감사 L-7). */
  @ParameterizedTest
  @ValueSource(
      strings = {
        "\uFF10\uFF11\uFF10-\uFF11\uFF12\uFF13\uFF14-\uFF15\uFF16\uFF17\uFF18",
        "010 / 1234 / 5678",
        "010_1234_5678",
        "010\u00A01234\u00A05678",
        "010\u200B1234\u200B5678",
        "0\u200B1\u200B0\u200B1234\u200B5678",
        "+82 10-1234-5678",
        "+82-010-1234-5678",
        "+821012345678",
        "0082 10 1234 5678",
        "010\u20141234\u20145678",
        "010\u22121234\u22125678",
        "010\u31611234\u31615678",
        "(010) 1234-5678",
        "\u0660\u0661\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668",
        "\uFF19\uFF17\uFF10\uFF11\uFF10\uFF11\uFF0D\uFF11\uFF12\uFF13\uFF14\uFF15\uFF16\uFF17",
        "970101\u2014 1234567",
        "970101 / 1234567"
      })
  void catchesDisguisedNumbers(String text) {
    assertThat(PersonalInfo.contains(text)).isTrue();
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "LH 콜센터 1600-1004",
        "SH 02-3410-7000",
        "공고번호 2026-123456",
        "보증금 24000000원, 월세 180000원",
        "접수 2026-10-26 ~ 2026-11-10",
        "1234567890123",
        "971332-1234567",
        "970101-9234567",
        "0101234567890123"
      })
  void letsOtherNumbersThrough(String text) {
    assertThat(PersonalInfo.contains(text)).isFalse();
  }

  @Test
  void plainTextIsFine() {
    assertThat(PersonalInfo.contains("버팀목 대출 같이 받을 수 있나요?")).isFalse();
  }
}
