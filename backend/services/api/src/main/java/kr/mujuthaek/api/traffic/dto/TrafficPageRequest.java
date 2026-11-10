package kr.mujuthaek.api.traffic.dto;

import io.swagger.v3.oas.annotations.media.Schema;

/**
 * 프론트 서버가 넘기는 화면 요청 한 건 (InternalTrafficController).
 *
 * @param path 화면 경로 ({@code /}로 시작)
 * @param userAgent 화면을 요청한 쪽의 User-Agent
 * @param ip 화면을 요청한 쪽의 IP
 */
public record TrafficPageRequest(
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED, description = "화면 경로 (/로 시작)") String path,
    String userAgent,
    String ip) {}
