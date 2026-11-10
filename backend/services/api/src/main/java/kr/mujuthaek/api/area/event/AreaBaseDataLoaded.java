package kr.mujuthaek.api.area.event;

import java.util.UUID;
import kr.mujuthaek.api.area.domain.AreaSource;

/**
 * area 기초 데이터(시설·상가)가 바뀌었음. 세권·점수 다시 계산(area 4·6·7단계)이 받아요.
 *
 * <p>트랜잭션 안에서 발행해서 {@code @TransactionalEventListener}·{@code @ApplicationModuleListener}로 받을 수
 * 있어요.
 *
 * @param scope 상가정보는 시도 이름, 나머지는 "ALL"
 * @param runId area.load_runs의 적재 기록
 */
public record AreaBaseDataLoaded(AreaSource source, String scope, UUID runId) {}
