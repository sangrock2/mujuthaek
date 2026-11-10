package kr.mujuthaek.api.user.dto.response;

import java.util.List;
import kr.mujuthaek.api.common.dto.response.MyReportResponse;

/** 내 제보 목록 (최근 100건, 최근 것부터) */
public record MyReportsResponse(List<MyReportResponse> items) {}
