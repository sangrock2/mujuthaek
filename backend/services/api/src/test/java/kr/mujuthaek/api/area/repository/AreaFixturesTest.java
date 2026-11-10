package kr.mujuthaek.api.area.repository;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

/**
 * area 테스트 자료가 바이트 그대로인지. 편집기·포매터가 인코딩이나 끝의 빈 줄을 바꾸면 적재 테스트는 통과해도 검사가 조용히 무의미해져서, 여기서 먼저 실패하게 해요.
 * 자료를 일부러 바꿨으면 아래 값도 같이 고쳐요 ({@code shasum -a 256 *.csv *.txt}).
 */
class AreaFixturesTest {

  private static final Map<String, String> SHA256 =
      new TreeMap<>(
          Map.ofEntries(
              Map.entry(
                  "boundary_sig.csv",
                  "7ead3c259db060fd56c45ec852dc5c8b735387f36b818fbbccf423e73d346596"),
              Map.entry(
                  "boundary_emd.csv",
                  "896c9cf75d9631aa733d0ae4e5cab2b05916374c2ab7c2ea19b23f6e50674bd1"),
              Map.entry(
                  "address_entrance_11.txt",
                  "446a23e69e56fd0e761832caea54cc52b2aab4f6fbb898181fa7b67b90c201e7"),
              Map.entry(
                  "address_entrance_48.txt",
                  "077280760a75ed353b5e12d2c372a18aff119bccec30eb0cbc6b93c4c12477ae"),
              Map.entry(
                  "address_entrance_26.txt",
                  "952110f28012d30d6ee95073fd494301efcc222bdfd6f6d59aaa75645b63fe97"),
              Map.entry(
                  "bus_stop.csv",
                  "dbcc1b6f1209395d62909f9f95a18f9182d12e326edee9fca9c9d7e79ff9f4ae"),
              Map.entry(
                  "bus_stop_150.csv",
                  "8177cb7ce25beb049b597db83cf9775e3766ee1f1619d5b75c6631adf0217d22"),
              Map.entry(
                  "bus_stop_small.csv",
                  "45a7579fac3e2c3eca75090d1b7e65109bc3239fbac64d937129726fe2f281e6"),
              Map.entry(
                  "hospital.csv",
                  "11ce2756d5a8951733e37a87fe5b4de04767db574c5e416dc46b674d9682a0e0"),
              Map.entry(
                  "hospital_no_coord_column.csv",
                  "0dfa1f8c8ba3060016cb8b11819a0ef2f73a0dde28a78d5764635005fedb93d2"),
              Map.entry(
                  "park.csv", "6edcc3b579d675a3d0985cf23972de432a35d22c1221206309ea1d454b4904f6"),
              Map.entry(
                  "school.csv", "5927cc86152cbb700ef55ffcb46ef4c07d97e38c729cc98db44c02e341e49715"),
              Map.entry(
                  "stores_gangwon.csv",
                  "34c42bbde97b9bf2d667b53e3bad234e6492fa98798e6113851e6e8493197eb0"),
              Map.entry(
                  "stores_gyeonggi.csv",
                  "206ec142d982da77128070b08cf84c5418032a8acf84127b665922db1121966a"),
              Map.entry(
                  "stores_real_header.csv",
                  "da4f291448a36e7c5709ebe87cafdcbd82c0094a3864cc2d237be33bea78053f"),
              Map.entry(
                  "subway_station.csv",
                  "36f7183deefc95961ac3a0b4c319399d0b6e3753456842545bff8ac0e4bf1ad8")));

  @Test
  void fixturesAreByteForByteUnchanged() throws Exception {
    Map<String, String> actual = new TreeMap<>();
    try (Stream<java.nio.file.Path> files =
        Files.list(PostgresAreaBaseDataLoaderTest.fixture("bus_stop.csv").getParent())) {
      for (var path :
          files
              .filter(p -> p.toString().endsWith(".csv") || p.toString().endsWith(".txt"))
              .toList()) {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path));
        actual.put(path.getFileName().toString(), HexFormat.of().formatHex(digest));
      }
    }
    assertThat(actual).isEqualTo(SHA256);
  }
}
