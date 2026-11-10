package kr.mujuthaek.api.area.domain;

/**
 * 가장 가까운 도시철도역.
 *
 * @param meters 직선거리 (m)
 * @param walkMinutes 도보 분 ({@link WalkMinutes}: 직선거리 × 1.3 ÷ 분속 67m, 올림)
 */
public record NearestStation(String name, long meters, int walkMinutes) {}
