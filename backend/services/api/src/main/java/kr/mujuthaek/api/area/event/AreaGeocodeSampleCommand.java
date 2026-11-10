package kr.mujuthaek.api.area.event;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import kr.mujuthaek.api.area.service.AddressLocator;
import kr.mujuthaek.api.area.service.GeocodeSampleReport;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/**
 * 주소 샘플 전체를 좌표로 바꿔 보고 성공률·방법별 비율·실패 이유를 마크다운으로 남기는 관리 명령 (계획 17번). 저장은 하지 않아요.
 *
 * <pre>
 * ./gradlew bootRun --args='--area.geocode-sample=cases --area.geocode-sample.out=../../.docs/area_geocode_sample.md'
 * </pre>
 *
 * <p>샘플은 정답 케이스와 같은 CSV(첫 칸 주소, 둘째 칸 종류, 14번째 칸 정답 주소 ID, 머리줄 있음). {@code cases}면 저장소의 정답 케이스 (test
 * 리소스 area/geocode/cases.csv)를 써요. 법정동코드 없이 주소 글자만으로 돌려요. 검색 API 키는 환경 변수로만 넣어요.
 */
@Component
@ConditionalOnProperty(name = "area.geocode-sample")
class AreaGeocodeSampleCommand implements ApplicationRunner {

  static final String BUNDLED_CASES =
      "src/test/resources/area/geocode/cases.csv"; // bootRun은 services/api에서 돌아요

  private final AddressLocator locator;
  private final ConfigurableApplicationContext context;
  private final Environment env;

  AreaGeocodeSampleCommand(
      AddressLocator locator, ConfigurableApplicationContext context, Environment env) {
    this.locator = locator;
    this.context = context;
    this.env = env;
  }

  @Override
  public void run(ApplicationArguments args) {
    int exit = 0;
    try {
      String sample = env.getRequiredProperty("area.geocode-sample");
      Path file = Path.of("cases".equals(sample) ? BUNDLED_CASES : sample);
      String report;
      try (InputStream in = Files.newInputStream(file)) {
        report = run(in, locator);
      }
      String out = env.getProperty("area.geocode-sample.out");
      if (out == null || out.isBlank()) {
        System.out.println(report);
      } else {
        Files.writeString(Path.of(out), report);
        System.out.println("보고서를 썼어요: " + out);
      }
    } catch (IOException | RuntimeException e) {
      System.out.println("실패: " + e.getMessage());
      exit = 1;
    }
    int code = exit;
    System.exit(SpringApplication.exit(context, () -> code));
  }

  /** 샘플 CSV를 돌려 보고서를 만들어요. */
  static String run(InputStream csv, AddressLocator locator) throws IOException {
    GeocodeSampleReport report = new GeocodeSampleReport();
    try (var in = new BufferedReader(new InputStreamReader(csv, StandardCharsets.UTF_8))) {
      in.readLine(); // 머리줄
      String line;
      while ((line = in.readLine()) != null) {
        if (line.isBlank()) {
          continue;
        }
        List<String> f = fields(line);
        String expected = f.size() > 13 && !f.get(13).isBlank() ? f.get(13) : null;
        report.add(
            new GeocodeSampleReport.Row(
                f.get(0), f.size() > 1 ? f.get(1) : "", expected, locator.locate(f.get(0), null)));
      }
    }
    return report.markdown();
  }

  /** CSV 한 줄 (큰따옴표 안의 쉼표·두 겹 따옴표). */
  static List<String> fields(String line) {
    List<String> out = new ArrayList<>();
    StringBuilder cur = new StringBuilder();
    boolean quoted = false;
    for (int i = 0; i < line.length(); i++) {
      char ch = line.charAt(i);
      if (quoted) {
        if (ch == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') {
          cur.append('"');
          i++;
        } else if (ch == '"') {
          quoted = false;
        } else {
          cur.append(ch);
        }
      } else if (ch == '"') {
        quoted = true;
      } else if (ch == ',') {
        out.add(cur.toString());
        cur.setLength(0);
      } else {
        cur.append(ch);
      }
    }
    out.add(cur.toString());
    return out;
  }
}
