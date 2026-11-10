package kr.mujuthaek.api;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

/** 모듈 경계 검사: 다른 모듈의 하위 패키지(service, repository …) 사용과 순환 의존을 막아요. */
class ModuleStructureTest {

  private final ApplicationModules modules = ApplicationModules.of(ApiApplication.class);

  @Test
  void verifiesModuleBoundaries() {
    modules.verify();
  }

  @Test
  void writesModuleDocs() {
    // build/spring-modulith-docs/ 에 모듈 관계 그림과 설명을 만들어요
    new Documenter(modules).writeDocumentation();
  }
}
