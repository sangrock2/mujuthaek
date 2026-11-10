package kr.mujuthaek.api.chat.domain;

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
