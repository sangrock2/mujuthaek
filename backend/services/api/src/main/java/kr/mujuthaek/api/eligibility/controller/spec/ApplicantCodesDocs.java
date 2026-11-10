package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.Schema;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import kr.mujuthaek.api.eligibility.rule.frame.Codes;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.stereotype.Component;

/**
 * 판정 입력(JudgmentApplicantRequest)의 유형·신청 제한 사유 칸에 고를 수 있는 코드를 문서에 보여요. 코드는 입력 검사(ApplicantMapper)와
 * 같은 {@link Codes}에서 읽어서 문서와 검사가 어긋나지 않아요. 문서가 꺼진 곳에서는 부르지 않아요.
 */
@Component
class ApplicantCodesDocs implements GlobalOpenApiCustomizer {

  private static final String APPLICANT = "JudgmentApplicantRequest";

  @Override
  public void customise(OpenAPI api) {
    if (api.getComponents() == null || api.getComponents().getSchemas() == null) {
      return;
    }
    Schema<?> applicant = api.getComponents().getSchemas().get(APPLICANT);
    if (applicant == null || applicant.getProperties() == null) {
      return;
    }
    choices(
        applicant.getProperties().get("statuses"),
        keys(
            Codes.HOUSING_STATUSES, Codes.BUSINESS_SPACE_STATUSES, Codes.STARTUP_SUPPORT_STATUSES));
    choices(
        applicant.getProperties().get("restrictions"),
        keys(Codes.BUSINESS_SPACE_RESTRICTIONS, Codes.STARTUP_SUPPORT_RESTRICTIONS));
  }

  @SuppressWarnings({"unchecked", "rawtypes"})
  private static void choices(Schema list, List<String> codes) {
    if (list != null && list.getItems() != null) {
      ((Schema) list.getItems()).setEnum(new ArrayList<>(codes));
    }
  }

  @SafeVarargs
  private static List<String> keys(Map<String, String>... maps) {
    Set<String> all = new LinkedHashSet<>();
    for (Map<String, String> map : maps) {
      all.addAll(map.keySet());
    }
    return List.copyOf(all);
  }
}
