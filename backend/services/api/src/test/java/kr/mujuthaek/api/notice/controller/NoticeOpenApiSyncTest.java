package kr.mujuthaek.api.notice.controller;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider;
import org.springframework.core.DefaultParameterNameDiscoverer;
import org.springframework.core.MethodIntrospector;
import org.springframework.core.MethodParameter;
import org.springframework.core.type.filter.AnnotationTypeFilter;
import org.springframework.stereotype.Controller;
import org.springframework.util.ClassUtils;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 공고 API 명세(contracts/openapi/notice.v1.json)가 지금 컨트롤러와 같은지: notice 모듈의 모든 컨트롤러에서 스프링이 실제로 만드는 요청
 * 매핑(경로·요청 방식)과 요청 값 이름(쿼리·경로)을 모아 명세와 양쪽으로 대조해요. 컨트롤러를 바꾸면 명세도 같이 고쳐야 통과해요.
 */
class NoticeOpenApiSyncTest {

  private static final String CONTROLLERS = "kr.mujuthaek.api.notice";
  private static final String SPEC = "/contracts/openapi/notice.v1.json";

  @Test
  void 명세의_경로와_요청_방식이_컨트롤러와_같다() {
    assertThat(spec().keySet()).isEqualTo(code().keySet());
  }

  @Test
  void 명세의_요청_값이_컨트롤러와_같다() {
    Map<String, Set<String>> spec = spec();
    code()
        .forEach(
            (operation, params) -> assertThat(spec.get(operation)).as(operation).isEqualTo(params));
  }

  /** 명세의 "GET /경로" → 요청 값("query:이름", "path:이름"). */
  private static Map<String, Set<String>> spec() {
    JsonNode root = read();
    Map<String, Set<String>> out = new TreeMap<>();
    for (var path : root.path("paths").properties()) {
      for (var operation : path.getValue().properties()) {
        if (!Set.of("get", "put", "post", "delete", "options", "head", "patch", "trace")
            .contains(operation.getKey())) {
          continue;
        }
        Set<String> params = new TreeSet<>();
        for (JsonNode param : operation.getValue().path("parameters")) {
          JsonNode resolved =
              param.has("$ref") ? root.at(param.get("$ref").asString().substring(1)) : param;
          params.add(resolved.path("in").asString() + ":" + resolved.path("name").asString());
        }
        out.put(operation.getKey().toUpperCase() + " " + path.getKey(), params);
      }
    }
    return out;
  }

  /** 컨트롤러의 "GET /경로" → 요청 값. 스프링 MVC가 쓰는 RequestMappingHandlerMapping으로 매핑을 만들어요. */
  private static Map<String, Set<String>> code() {
    Mappings mappings = new Mappings();
    mappings.afterPropertiesSet();
    var scanner = new ClassPathScanningCandidateComponentProvider(false);
    scanner.addIncludeFilter(new AnnotationTypeFilter(Controller.class));
    Map<String, Set<String>> out = new TreeMap<>();
    for (var candidate : scanner.findCandidateComponents(CONTROLLERS)) {
      Class<?> type = ClassUtils.resolveClassName(candidate.getBeanClassName(), null);
      Map<Method, RequestMappingInfo> methods =
          MethodIntrospector.selectMethods(
              type,
              (MethodIntrospector.MetadataLookup<RequestMappingInfo>)
                  method -> mappings.mappingFor(method, type));
      methods.forEach(
          (method, info) -> {
            Set<RequestMethod> verbs = info.getMethodsCondition().getMethods();
            assertThat(verbs).as("요청 방식이 정해지지 않은 매핑 " + method).isNotEmpty();
            for (String path : info.getPatternValues()) {
              for (RequestMethod verb : verbs) {
                out.put(verb.name() + " " + path, params(method));
              }
            }
          });
    }
    assertThat(out).as("notice 컨트롤러 매핑").isNotEmpty();
    return out;
  }

  private static Set<String> params(Method method) {
    Set<String> out = new TreeSet<>();
    for (int i = 0; i < method.getParameterCount(); i++) {
      MethodParameter parameter = new MethodParameter(method, i);
      parameter.initParameterNameDiscovery(new DefaultParameterNameDiscoverer());
      RequestParam query = parameter.getParameterAnnotation(RequestParam.class);
      PathVariable path = parameter.getParameterAnnotation(PathVariable.class);
      if (query != null) {
        out.add("query:" + (query.name().isEmpty() ? parameter.getParameterName() : query.name()));
      } else if (path != null) {
        out.add("path:" + (path.name().isEmpty() ? parameter.getParameterName() : path.name()));
      }
    }
    return out;
  }

  private static JsonNode read() {
    try (InputStream input = NoticeOpenApiSyncTest.class.getResourceAsStream(SPEC)) {
      assertThat(input).as(SPEC).isNotNull();
      return JsonMapper.builder().build().readTree(input);
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }

  /** 애플리케이션 컨텍스트 없이 매핑 규칙만 쓰려고 빈 찾기를 끈 RequestMappingHandlerMapping. */
  private static final class Mappings extends RequestMappingHandlerMapping {

    @Override
    protected void initHandlerMethods() {}

    RequestMappingInfo mappingFor(Method method, Class<?> type) {
      return getMappingForMethod(method, type);
    }
  }
}
