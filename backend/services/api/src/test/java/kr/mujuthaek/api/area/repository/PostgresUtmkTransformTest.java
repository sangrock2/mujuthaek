package kr.mujuthaek.api.area.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.Coordinate;
import org.junit.jupiter.api.Test;

class PostgresUtmkTransformTest {

  private final PostgresUtmkTransform transform =
      new PostgresUtmkTransform(AreaTestDatabase.dataSource());

  @Test
  void seoulCityHallComesOutWhereTheAddressLoaderPutsIt() {
    // 도로명주소 원천의 서울시청 출입구 (fixtures/address_entrance_11.txt, 적재 테스트가 37.5665, 126.978로 확인)
    Coordinate p = transform.toWgs84(953901.165312, 1952032.080979);

    assertThat(p.lat()).isCloseTo(37.5665, within(0.0001));
    assertThat(p.lng()).isCloseTo(126.978, within(0.001));
  }
}
