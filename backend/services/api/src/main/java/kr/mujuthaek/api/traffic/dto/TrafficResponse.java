package kr.mujuthaek.api.traffic.dto;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.traffic.log.RequestLogStore;

/**
 * 관리자 트래픽 화면 응답.
 *
 * @param asOf 만든 시각
 * @param days 기간(오늘 포함 최근 며칠)
 * @param ga Google Analytics 숫자(방문·유입·기기·이용 흐름)
 * @param server api 서버 요청 기록 숫자(가입·로그인·사람/봇 요청)
 */
public record TrafficResponse(
    Instant asOf, int days, Ga ga, List<RequestLogStore.ServerDaily> server) {

  /**
   * @param connected GA를 불러왔는지. 설정이 없거나 실패하면 false이고 아래 목록은 비어요
   * @param error 실패 이유(관리자에게 보여 줄 문장, 키 내용 없음)
   * @param fetchedAt GA에서 가져온 시각(한 시간 정도 다시 쓰여요)
   */
  public record Ga(
      boolean connected,
      String error,
      Instant fetchedAt,
      List<Daily> daily,
      List<Item> channels,
      List<Item> sources,
      List<Item> campaigns,
      List<Item> landingPages,
      List<Item> pages,
      List<Item> devices,
      List<Item> browsers,
      List<Item> regions,
      List<FunnelStep> funnel,
      List<NoticeView> popularNotices) {

    public static Ga off(String error) {
      return new Ga(
          false, error, null, List.of(), List.of(), List.of(), List.of(), List.of(), List.of(),
          List.of(), List.of(), List.of(), List.of(), List.of());
    }
  }

  /** GA 일별: 활성 사용자·신규 사용자·세션·페이지뷰. */
  public record Daily(
      LocalDate date, long activeUsers, long newUsers, long sessions, long pageViews) {}

  /**
   * 목록 한 줄.
   *
   * @param value 주 값(유입·방문 페이지는 세션, 페이지는 페이지뷰, 기기·브라우저·지역은 활성 사용자)
   * @param users 활성 사용자
   */
  public record Item(String name, long value, long users) {}

  /**
   * 이용 흐름 한 단계(GA 이벤트).
   *
   * @param event GA 이벤트 이름
   * @param label 화면 이름
   * @param count 이벤트 수
   * @param users 그 이벤트를 한 사용자 수
   */
  public record FunnelStep(String event, String label, long count, long users) {}

  /**
   * 많이 본 공고 한 줄. 공고 제목은 화면이 공고 ID로 찾아요(traffic 모듈은 notice를 부르지 않아요).
   *
   * @param noticeId 공고 상세 주소(/notices/{id})의 ID
   * @param views 페이지뷰
   * @param users 본 사람(경로별 활성 사용자를 더한 값이라 겹친 사람이 있으면 조금 많아요)
   */
  public record NoticeView(String noticeId, long views, long users) {}
}
