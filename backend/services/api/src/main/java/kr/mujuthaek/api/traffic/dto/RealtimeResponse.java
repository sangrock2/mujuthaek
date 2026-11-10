package kr.mujuthaek.api.traffic.dto;

import java.time.Instant;
import java.util.List;

/**
 * 지금 접속자 (GA 실시간 보고서, 동의한 사람만).
 *
 * @param connected GA를 불러왔는지. 설정이 없거나 실패하면 false
 * @param error 실패 이유(관리자에게 보여 줄 문장)
 * @param fetchedAt GA에서 가져온 시각(30초 정도 다시 쓰여요)
 * @param last30Minutes 최근 30분 활성 사용자
 * @param last5Minutes 최근 5분 활성 사용자
 * @param devices 최근 30분 기기별 활성 사용자
 */
public record RealtimeResponse(
    boolean connected,
    String error,
    Instant fetchedAt,
    long last30Minutes,
    long last5Minutes,
    List<TrafficResponse.Item> devices) {

  public static RealtimeResponse off(String error) {
    return new RealtimeResponse(false, error, null, 0, 0, List.of());
  }
}
