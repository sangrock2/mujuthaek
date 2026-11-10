package kr.mujuthaek.api.common.event;

import java.util.UUID;

/**
 * 관리자가 중복 의심 정책 사업 중 나중 것을 숨김(「나중 것 숨김」). 숨긴 사업은 열린 목록·판정·알림에서 빠져요. user가 받아 숨긴 사업에 둔 관심을 남은 사업으로
 * 옮겨요: 그대로 두면 관심 목록에 빈 줄로 남고, 남은 사업의 마감·정정 알림을 받지 못했어요(2026-11-10 재검토). 숨김과 같은 트랜잭션에서 받아요.
 *
 * @param hiddenPolicyId 숨긴 사업 (rawPolicyId)
 * @param keptPolicyId 남은 사업 (먼저 있던 것, rawPolicyId)
 */
public record PolicyHidden(UUID hiddenPolicyId, UUID keptPolicyId) {}
