package kr.mujuthaek.api.common.config;

import static org.assertj.core.api.Assertions.assertThat;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.core.type.filter.AnnotationTypeFilter;
import org.springframework.util.ClassUtils;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * API 설명 규칙: 모든 컨트롤러는 같은 이름의 spec 인터페이스({@code XxxController} → {@code spec.XxxApiSpec})를 구현하고, 그
 * 인터페이스에는 {@code @Tag}, 핸들러마다 {@code @Operation(summary)}가 있어요. 새 컨트롤러나 API를 만들고 설명을 빠뜨리면 여기서 실패해요.
 */
class ApiSpecConventionTest {

  @Test
  void 모든_컨트롤러가_같은_이름의_spec_인터페이스를_구현한다() {
    for (Class<?> controller : controllers()) {
      Class<?> spec = spec(controller);
      assertThat(spec).as(controller.getName() + "의 spec 인터페이스").isNotNull();
      assertThat(spec.getPackageName()).as(spec.getName()).endsWith(".spec");
      assertThat(spec.isAnnotationPresent(Tag.class)).as(spec.getName() + "의 @Tag").isTrue();
    }
  }

  @Test
  void 모든_핸들러가_spec에_요약을_가진다() {
    for (Class<?> controller : controllers()) {
      Class<?> spec = spec(controller);
      assertThat(spec).as(controller.getName() + "의 spec 인터페이스").isNotNull();
      for (Method handler : handlers(controller)) {
        String name = controller.getSimpleName() + "." + handler.getName();
        Method declared = declaredIn(spec, handler);
        assertThat(declared).as(name + "가 " + spec.getSimpleName() + "에 없어요").isNotNull();
        Operation operation = declared.getAnnotation(Operation.class);
        assertThat(operation).as(name + "의 @Operation").isNotNull();
        assertThat(operation.summary()).as(name + "의 summary").isNotBlank();
      }
    }
  }

  @Test
  void 태그_이름이_겹치지_않는다() {
    List<String> names =
        controllers().stream().map(c -> spec(c).getAnnotation(Tag.class).name()).toList();
    assertThat(names).as("스웨거 화면에서 두 컨트롤러가 한 묶음으로 섞여요").doesNotHaveDuplicates();
  }

  private static List<Class<?>> controllers() {
    var scanner = new ClassPathScanningCandidateComponentProvider(false);
    scanner.addIncludeFilter(new AnnotationTypeFilter(RestController.class));
    List<Class<?>> found =
        scanner.findCandidateComponents("kr.mujuthaek.api").stream()
            .<Class<?>>map(bean -> ClassUtils.resolveClassName(bean.getBeanClassName(), null))
            .filter(ApiSpecConventionTest::inMain) // 테스트 코드 안의 가짜 컨트롤러는 빼요
            .toList();
    assertThat(found).as("컨트롤러를 못 찾으면 이 시험이 아무것도 안 봐요").hasSizeGreaterThan(30);
    return found;
  }

  private static boolean inMain(Class<?> type) {
    return !type.getProtectionDomain().getCodeSource().getLocation().getPath().contains("/test/");
  }

  private static Class<?> spec(Class<?> controller) {
    String expected = controller.getSimpleName().replaceFirst("Controller$", "ApiSpec");
    return Arrays.stream(controller.getInterfaces())
        .filter(i -> i.getSimpleName().equals(expected))
        .findFirst()
        .orElse(null);
  }

  private static List<Method> handlers(Class<?> controller) {
    return Arrays.stream(controller.getDeclaredMethods())
        .filter(m -> AnnotatedElementUtils.hasAnnotation(m, RequestMapping.class))
        .toList();
  }

  private static Method declaredIn(Class<?> spec, Method handler) {
    try {
      return spec.getMethod(handler.getName(), handler.getParameterTypes());
    } catch (NoSuchMethodException e) {
      return null;
    }
  }
}
