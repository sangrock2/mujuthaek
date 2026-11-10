package kr.mujuthaek.api.user.security;

import java.util.List;
import java.util.stream.Stream;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 로그인 화면 연결 설정 (application.yml의 app.*).
 *
 * @param frontendUrl 로그인 뒤 돌아갈 프론트 주소. CORS로 허용하는 주소이기도 해요
 * @param corsOrigins frontendUrl 말고도 CORS로 허용할 프론트 주소 (로컬 다른 포트, 미리보기 배포 등)
 */
@ConfigurationProperties("app")
record LoginProperties(String frontendUrl, List<String> corsOrigins) {

  /** CORS로 허용할 주소: frontendUrl + corsOrigins (빈 칸·중복 제외). */
  List<String> allowedOrigins() {
    var extra = corsOrigins == null ? List.<String>of() : corsOrigins;
    return Stream.concat(Stream.of(frontendUrl), extra.stream())
        .filter(origin -> origin != null && !origin.isBlank())
        .map(String::strip)
        .distinct()
        .toList();
  }
}
