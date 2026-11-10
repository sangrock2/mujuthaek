package kr.mujuthaek.api.notice.dto.response;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/**
 * 지도 (GET /notices/map). 지도 범위 안 공고가 300개 이하면 핀, 넘으면 지역별 묶음(클러스터)만 줘요.
 *
 * @param clusters 지역별 묶음 (핀을 줄 때는 빈 목록)
 * @param pins 공고 핀 (묶음을 줄 때는 빈 목록)
 */
public record NoticeMapResponse(List<Cluster> clusters, List<Pin> pins) {

  /**
   * @param regionCode 묶은 지역 (확대가 작으면 시도 2자리, 아니면 시군구 5자리. 지역을 모르면 null)
   * @param lat 묶음 안 공고 좌표의 평균
   */
  public record Cluster(String regionCode, String regionName, int count, double lat, double lng) {}

  /** 공고 대표 위치의 핀. */
  public record Pin(
      UUID id, String title, String noticeType, LocalDate applyEnd, double lat, double lng) {}
}
