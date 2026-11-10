package kr.mujuthaek.api.notification.service.internal;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** 알림 요청을 만들 때 회원마다 보낼 구독 기기 (최근에 쓴 기기부터, 최대 5대). 기기가 없는 회원은 결과에 없어요. */
@FunctionalInterface
public interface PushDeviceFinder {

  Map<UUID, List<PushDevice>> latest(Collection<UUID> userIds);
}
