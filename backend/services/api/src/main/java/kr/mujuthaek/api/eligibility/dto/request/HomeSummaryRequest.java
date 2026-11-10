package kr.mujuthaek.api.eligibility.dto.request;

import jakarta.validation.Valid;

/** 홈 요약 요청 (POST /home/summary). 맞춤 목록과 같은 필터(찾아볼 지역 등)와 판정 입력(구간 값)을 받아요. 판정 입력은 저장하지 않아요. */
public record HomeSummaryRequest(
    @Valid NoticeSearchRequest.Filters filters, @Valid ApplicantRequest applicant) {

  public NoticeSearchRequest.Filters filtersOrEmpty() {
    return filters == null
        ? new NoticeSearchRequest.Filters(null, null, null, null, null, null, null)
        : filters;
  }
}
