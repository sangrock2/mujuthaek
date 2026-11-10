package kr.mujuthaek.api.notice.controller;

import kr.mujuthaek.api.notice.client.CollectorAdminClient;
import kr.mujuthaek.api.notice.controller.spec.AdminSourceApiSpec;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.JsonNode;

/** 관리자 수집 현황 (설명은 {@link AdminSourceApiSpec}). */
@RestController
@RequestMapping("/api/admin/sources")
class AdminSourceController implements AdminSourceApiSpec {

  private final CollectorAdminClient collector;

  AdminSourceController(CollectorAdminClient collector) {
    this.collector = collector;
  }

  @Override
  @GetMapping
  public JsonNode sources() {
    return collector.sources();
  }

  @Override
  @PostMapping("/{code}/pause")
  public JsonNode pause(@PathVariable String code) {
    return collector.setEnabled(code, false);
  }

  @Override
  @PostMapping("/{code}/run")
  public JsonNode run(@PathVariable String code) {
    return collector.runNow(code);
  }

  @Override
  @PostMapping("/{code}/resume")
  public JsonNode resume(@PathVariable String code) {
    return collector.setEnabled(code, true);
  }
}
