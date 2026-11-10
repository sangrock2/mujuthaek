package kr.mujuthaek.api.notice.service.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 추출 비용·품질: 기간을 1~90으로 맞춰 추출 서비스 집계를 그대로 넘겨요 (DB 없이). */
class AdminExtractionStatsServiceTest {

  final ExtractionReviewClient client = mock(ExtractionReviewClient.class);
  final AdminExtractionStatsService service = new AdminExtractionStatsService(client);

  @Test
  void daysOutOfRangeAreClampedAndTheBodyIsPassedThrough() {
    var body = JsonMapper.builder().build().readTree("{\"days\":90,\"notices\":12}");
    when(client.extractionStats(anyInt())).thenReturn(body);

    assertThat(service.stats(365).get("notices").asInt()).isEqualTo(12);
    verify(client).extractionStats(90);
    service.stats(0);
    verify(client).extractionStats(1);
  }

  @Test
  void emptyAnswerIsUnavailable() {
    when(client.extractionStats(anyInt())).thenReturn(null);
    assertThatThrownBy(() -> service.stats(7)).isInstanceOf(CustomException.class);
  }
}
