package kr.mujuthaek.api.area.dto.response;

import java.util.List;
import kr.mujuthaek.api.area.domain.SiteScore;

/** POST /areas/score 응답. 요청한 위치마다 점수 한 줄 (요청 순서, 없는 위치는 빠져요). */
public record AreaScoreResponse(List<SiteScore> items) {}
