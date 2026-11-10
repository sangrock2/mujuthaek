package kr.mujuthaek.api.notice.dto.response;

import java.util.UUID;

/** 받은 제보. status는 NEW. */
public record NoticeReportCreatedResponse(UUID id, String status) {}
