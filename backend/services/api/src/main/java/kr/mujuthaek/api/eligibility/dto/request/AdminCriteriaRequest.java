package kr.mujuthaek.api.eligibility.dto.request;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;
import tools.jackson.databind.JsonNode;

/**
 * 관리자가 넣는 한 해 기준값.
 *
 * @param validFrom 쓰기 시작하는 날 (비우면 그해 1월 1일). 미래 날짜면 그날 0시부터 판정에 쓰여요(예약 적용)
 * @param data 값. 소득 기준은 {"monthlyWon": {"1": 2564238, "2": …}}, 순위 요건은 {"ranks": [...]}
 * @param source 근거 (고시 번호·공고 이름)
 */
public record AdminCriteriaRequest(
    LocalDate validFrom, @NotNull JsonNode data, @Size(max = 300) String source) {}
