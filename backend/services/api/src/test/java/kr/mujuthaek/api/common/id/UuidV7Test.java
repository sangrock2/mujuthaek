package kr.mujuthaek.api.common.id;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class UuidV7Test {

  @Test
  void version7AndOrderedEvenWithinTheSameMillisecond() {
    List<UUID> ids = new ArrayList<>();
    for (int i = 0; i < 5000; i++) {
      ids.add(UuidV7.next());
    }
    assertThat(ids).allSatisfy(id -> assertThat(id.version()).isEqualTo(7));
    assertThat(ids).allSatisfy(id -> assertThat(id.variant()).isEqualTo(2));
    assertThat(new HashSet<>(ids)).hasSize(ids.size());
    List<String> asText = ids.stream().map(UUID::toString).toList();
    assertThat(asText).isSorted();
  }
}
