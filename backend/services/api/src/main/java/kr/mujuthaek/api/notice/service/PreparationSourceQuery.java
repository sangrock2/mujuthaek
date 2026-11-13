package kr.mujuthaek.api.notice.service;

import java.time.Clock;
import java.time.LocalDate;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.mapper.NoticeDetailMapper;
import kr.mujuthaek.api.notice.repository.PreparationSourceRepository;
import org.springframework.stereotype.Service;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** 다른 모듈에 제공하는 준비용 일괄 projection. 판정 입력·생활권은 포함하지 않는다. */
@Service
public class PreparationSourceQuery {
  private final PreparationSourceRepository repository;
  private final JsonMapper json;
  private final Clock clock;

  public PreparationSourceQuery(
      PreparationSourceRepository repository, JsonMapper json, Clock clock) {
    this.repository = repository;
    this.json = json;
    this.clock = clock;
  }

  public Map<UUID, PreparationSource> findAll(Collection<UUID> ids) {
    Map<UUID, PreparationSource> result = new HashMap<>();
    LocalDate today = LocalDate.now(clock);
    for (var r : repository.findAll(ids)) {
      var header =
          new NoticeDetailResponse.Header(
              r.id(),
              r.field(),
              r.title(),
              r.provider(),
              null,
              null,
              r.status(),
              r.applyStart(),
              r.applyEnd(),
              null,
              null,
              null,
              null,
              r.detailUrl(),
              false);
      var followUps =
          json.readTree(r.followUps())
              .valueStream()
              .map(
                  f ->
                      NoticeDetailMapper.followUp(
                          f.path("title").asString(),
                          f.path("detailUrl").asString(null),
                          f.path("postedOn").isNull()
                              ? null
                              : LocalDate.parse(f.path("postedOn").asString()),
                          f.path("schedules"),
                          today))
              .toList();
      var detail =
          NoticeDetailMapper.map(
              header,
              json.readTree(r.payload()),
              List.of(),
              followUps,
              r.version(),
              r.reviewed(),
              r.updatedAt(),
              today);
      ObjectNode tree = json.valueToTree(detail);
      ObjectNode content = json.createObjectNode();
      content.put("snapshotVersion", 1);
      for (String key :
          List.of(
              "header",
              "schedules",
              "requiredDocuments",
              "followUps",
              "unitTypes",
              "conditions",
              "heldItems",
              "files",
              "guidance",
              "selectionRules")) content.set(key, tree.path(key));
      result.put(
          r.requestedId(),
          new PreparationSource(
              r.id(),
              r.field(),
              r.version(),
              r.version() + ":" + PreparationSource.fingerprint(content),
              content));
    }
    return result;
  }
}
