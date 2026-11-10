package kr.mujuthaek.api.traffic.dto;

import java.time.Instant;
import java.util.List;
import kr.mujuthaek.api.traffic.log.RequestLogStore;

/**
 * 관리자 트래픽 「봇·보안」 탭. 모두 api 서버 요청 기록이에요(페이지만 긁는 봇은 프론트 서버 앞단 기록이 있어야 보여요).
 *
 * @param clients 날짜·보낸 쪽(HUMAN·SEARCH_BOT·PREVIEW_BOT·TOOL·MONITOR·UNKNOWN)별 요청 수
 * @param topSources 요청이 많은 곳(가린 IP, 원본 IP가 지워진 기록은 그날 해시)
 * @param topBotPaths 사람이 아닌 요청이 많이 온 경로
 * @param statuses 거절·오류 응답 수
 * @param adminAccess 최근 관리자 API 요청
 * @param loginFailures 최근 로그인 실패
 */
public record BotTrafficResponse(
    Instant asOf,
    int days,
    List<RequestLogStore.ClientDaily> clients,
    List<RequestLogStore.TopSource> topSources,
    List<RequestLogStore.PathCount> topBotPaths,
    List<RequestLogStore.StatusCount> statuses,
    List<RequestLogStore.Access> adminAccess,
    List<RequestLogStore.Access> loginFailures) {}
