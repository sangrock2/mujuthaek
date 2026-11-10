package kr.mujuthaek.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * API 문서(스웨거)가 실제 API와 같은지: 세 그룹(사용자·관리자·내부) 문서를 합치면 서버의 {@code /api/**} 요청 매핑과 빠짐없이 같고, 모든 API에
 * 요약과 태그가 있어요. 로그인·관리자 경로의 자물쇠와 401·403, API 이름(컨트롤러_메서드), 응답마다의 오류 예시는 OpenApiConfig가 붙여요.
 */
@SpringBootTest(properties = "spring.rabbitmq.listener.simple.auto-startup=false")
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class OpenApiDocsTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  @Autowired MockMvc mvc;

  @Autowired
  @Qualifier("requestMappingHandlerMapping")
  RequestMappingHandlerMapping mappings;

  @Test
  void 문서가_모든_API를_요약과_함께_담는다() throws Exception {
    Set<String> documented = new TreeSet<>();
    for (String group : List.of("user", "admin", "internal")) {
      for (var path : docs(group).path("paths").properties()) {
        for (var operation : path.getValue().properties()) {
          String name = operation.getKey().toUpperCase() + " " + path.getKey();
          documented.add(name);
          assertThat(operation.getValue().path("summary").asString()).as(name).isNotBlank();
          assertThat(operation.getValue().path("tags").isEmpty()).as(name + "의 태그").isFalse();
        }
      }
    }
    assertThat(documented).isEqualTo(code());
  }

  @Test
  void 로그인_경로는_자물쇠와_401_관리자_경로는_403까지_가진다() throws Exception {
    for (String group : List.of("user", "admin")) {
      JsonNode doc = docs(group);
      assertThat(doc.path("components").path("schemas").has("Problem")).isTrue();
      for (var path : doc.path("paths").properties()) {
        boolean admin = path.getKey().startsWith("/api/admin/");
        if (!admin && !path.getKey().startsWith("/api/users/")) {
          continue;
        }
        for (var operation : path.getValue().properties()) {
          String name = operation.getKey().toUpperCase() + " " + path.getKey();
          JsonNode responses = operation.getValue().path("responses");
          assertThat(operation.getValue().path("security").toString())
              .as(name)
              .contains("accessToken");
          assertThat(responses.has("401")).as(name).isTrue();
          assertThat(responses.has("403")).as(name).isEqualTo(admin);
        }
      }
    }
  }

  @Test
  void API_이름은_컨트롤러_메서드이고_겹치지_않는다() throws Exception {
    Set<String> ids = new TreeSet<>();
    for (String group : List.of("user", "admin", "internal")) {
      for (var path : docs(group).path("paths").properties()) {
        for (var operation : path.getValue().properties()) {
          String name = operation.getKey().toUpperCase() + " " + path.getKey();
          String id = operation.getValue().path("operationId").asString();
          assertThat(id).as(name).matches("[A-Z][A-Za-z0-9]*_[a-z][A-Za-z0-9]*");
          assertThat(ids.add(id)).as(name + "의 이름 " + id + "이 겹쳐요").isTrue();
        }
      }
    }
  }

  @Test
  void 오류_예시는_그_응답_설명의_code와_상태다() throws Exception {
    for (String group : List.of("user", "admin")) {
      for (var path : docs(group).path("paths").properties()) {
        for (var operation : path.getValue().properties()) {
          for (var response : operation.getValue().path("responses").properties()) {
            String status = response.getKey();
            if (!status.startsWith("4") && !status.startsWith("5")) {
              continue;
            }
            String name = operation.getKey().toUpperCase() + " " + path.getKey() + " " + status;
            String description = response.getValue().path("description").asString();
            assertThat(description).as(name).matches("(?s)[A-Z][A-Z0-9_]+ — .*");
            JsonNode example =
                response
                    .getValue()
                    .path("content")
                    .path("application/problem+json")
                    .path("example");
            assertThat(example.path("code").asString())
                .as(name)
                .isEqualTo(description.substring(0, description.indexOf(" — ")));
            assertThat(example.path("status").asInt()).as(name).isEqualTo(Integer.parseInt(status));
          }
        }
      }
    }
  }

  @Test
  void 성공_응답은_기본_문구가_아니고_프레임워크_타입을_본문으로_보이지_않는다() throws Exception {
    for (String group : List.of("user", "admin", "internal")) {
      JsonNode doc = docs(group);
      assertThat(doc.path("components").path("schemas").propertyNames())
          .as(group + " 스키마에 스프링 타입이 보이면 화면에 그 클래스 칸이 나와요")
          .doesNotContain("SseEmitter", "ResponseBodyEmitter", "ResponseEntity");
      for (var path : doc.path("paths").properties()) {
        for (var operation : path.getValue().properties()) {
          for (var response : operation.getValue().path("responses").properties()) {
            if (!response.getKey().startsWith("2")) {
              continue;
            }
            String name =
                operation.getKey().toUpperCase() + " " + path.getKey() + " " + response.getKey();
            assertThat(response.getValue().path("description").asString())
                .as(name)
                .isNotIn("OK", "Created", "Accepted", "No Content");
          }
        }
      }
    }
  }

  @Test
  void 칸_모양과_검사가_실제와_같게_보인다() throws Exception {
    JsonNode user = docs("user");
    JsonNode admin = docs("admin");
    for (String group : List.of("user", "admin", "internal")) {
      String text = docs(group).toString();
      assertThat(text).as(group + ": Jackson JsonNode 내부 칸").doesNotContain("\"nodeType\"");
      assertThat(text).as(group + ": 표시용 확장 칸이 남음").doesNotContain("x-not-empty");
      for (JsonNode schema : docs(group).path("components").path("schemas")) {
        for (var property : schema.path("properties").properties()) {
          for (JsonNode s : List.of(property.getValue(), property.getValue().path("items"))) {
            String pattern = s.path("pattern").asString("");
            assertThat(pattern.isEmpty() || (pattern.startsWith("^") && pattern.endsWith("$")))
                .as(group + " " + property.getKey() + " pattern " + pattern)
                .isTrue();
          }
        }
      }
    }
    JsonNode schemas = admin.path("components").path("schemas");
    assertThat(
            schemas
                .path("AdminRequestsSuspend")
                .path("properties")
                .path("reason")
                .path("minLength")
                .asInt())
        .as("@NotBlank @Size(max)")
        .isEqualTo(1);
    JsonNode role = schemas.path("RoleChangeRequest").path("properties").path("role");
    assertThat(role.path("enum").toString()).isEqualTo("[\"USER\",\"ADMIN\"]");
    assertThat(role.has("pattern")).isFalse();
    assertThat(
            user.path("components")
                .path("schemas")
                .path("ApplicantRequest")
                .path("properties")
                .path("birthMonth")
                .path("pattern")
                .asString())
        .as("YearMonth")
        .isNotBlank();
  }

  @Test
  void 스웨거_화면은_사용자_API부터_연다() throws Exception {
    String body =
        mvc.perform(get("/v3/api-docs/swagger-config"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    JsonNode config = JSON.readTree(body);
    String primary = config.path("urls.primaryName").asString();
    // 화면은 urls의 name(묶음 표시 이름)으로 찾아요. 맞는 게 없으면 이름순 첫 묶음(관리자 API)이 열려요
    JsonNode opened = null;
    for (JsonNode url : config.path("urls")) {
      if (url.path("name").asString().equals(primary)) {
        opened = url;
      }
    }
    assertThat(opened).as("urls.primaryName " + primary + "에 맞는 묶음").isNotNull();
    assertThat(opened.path("url").asString()).endsWith("/v3/api-docs/user");
  }

  @Test
  void 스웨거_화면이_열린다() throws Exception {
    mvc.perform(get("/swagger-ui/index.html")).andExpect(status().isOk());
  }

  private JsonNode docs(String group) throws Exception {
    String body =
        mvc.perform(get("/v3/api-docs/" + group))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    return JSON.readTree(body);
  }

  /** 서버가 실제로 만드는 {@code /api/**} 요청 매핑: "GET /api/v1/regions" 꼴. */
  private Set<String> code() {
    Set<String> out = new TreeSet<>();
    mappings
        .getHandlerMethods()
        .keySet()
        .forEach(
            info ->
                info.getPathPatternsCondition().getPatternValues().stream()
                    .filter(path -> path.startsWith("/api/"))
                    .forEach(
                        path ->
                            info.getMethodsCondition()
                                .getMethods()
                                .forEach(method -> out.add(method.name() + " " + path))));
    assertThat(out).as("요청 매핑을 못 찾으면 이 시험이 아무것도 안 봐요").hasSizeGreaterThan(100);
    return out;
  }
}
