package kr.mujuthaek.api.traffic.controller;

import kr.mujuthaek.api.traffic.controller.spec.AdminTrafficApiSpec;
import kr.mujuthaek.api.traffic.dto.BotTrafficResponse;
import kr.mujuthaek.api.traffic.dto.RealtimeResponse;
import kr.mujuthaek.api.traffic.dto.TrafficResponse;
import kr.mujuthaek.api.traffic.service.TrafficService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 관리자 「트래픽」 화면 (설명은 {@link AdminTrafficApiSpec}). */
@RestController
@RequestMapping("/api/admin/traffic")
class AdminTrafficController implements AdminTrafficApiSpec {

  private final TrafficService traffic;

  AdminTrafficController(TrafficService traffic) {
    this.traffic = traffic;
  }

  @Override
  @GetMapping
  public TrafficResponse traffic(@RequestParam(defaultValue = "7") int days) {
    return traffic.traffic(Math.clamp(days, 1, 90));
  }

  @Override
  @GetMapping("/realtime")
  public RealtimeResponse realtime() {
    return traffic.realtime();
  }

  @Override
  @GetMapping("/bots")
  public BotTrafficResponse bots(@RequestParam(defaultValue = "7") int days) {
    return traffic.bots(Math.clamp(days, 1, 30));
  }
}
