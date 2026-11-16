"use client";

import { useCallback, useEffect, useState } from "react";
import { isMember, useSession } from "@/features/auth/session";
import {
  isPushSupported,
  subscribePush,
  syncExistingPushSubscription,
  unsubscribePush,
} from "@/shared/lib/push";

/**
 * 이 브라우저의 푸시 알림 구독 상태.
 * 지원하지 않는 브라우저거나 구독에 실패하면 꺼진 상태로 남아요.
 */
export function usePush() {
  const session = useSession();
  const userId = isMember(session.data) ? session.data.id : null;
  const [state, setState] = useState<{ userId: string; enabled: boolean } | null>(null);
  // 이전 계정의 확인 결과를 새 계정에 켜짐으로 표시하지 않아요.
  const enabled = !!userId && state?.userId === userId && state.enabled;
  const checked = !session.isPending && (!userId || state?.userId === userId);
  const [pending, setPending] = useState(false);
  /** 켜기에 실패한 이유 (화면에 보여 줘요) */
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    if (session.isPending) return;
    if (!userId) return;
    // 지원하지 않거나 서비스 워커가 아직 없으면 구독 없음 (ready는 등록이 실패하면 끝나지 않아서 쓰지 않아요)
    (isPushSupported() ? syncExistingPushSubscription(() => alive) : Promise.resolve(null))
      .then((sub) => {
        if (alive) setState({ userId, enabled: !!sub });
      })
      .catch(() => {
        if (alive) {
          setState({ userId, enabled: false });
          setError("이 브라우저의 알림 설정을 확인하지 못했어요. 알림을 다시 켜 주세요.");
        }
      });
    return () => {
      alive = false;
    };
  }, [userId, session.isPending]);

  const turnOn = useCallback(async () => {
    if (!userId) {
      setError("로그인한 뒤 알림을 켜 주세요.");
      return false;
    }
    if (!isPushSupported()) {
      setError("이 브라우저는 웹 푸시 알림을 지원하지 않아요.");
      return false;
    }
    setPending(true);
    setError(null);
    try {
      await subscribePush();
      setState({ userId, enabled: true });
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "알림을 켜지 못했어요.");
      return false;
    } finally {
      setPending(false);
    }
  }, [userId]);

  const turnOff = useCallback(async () => {
    if (!userId || !isPushSupported()) return;
    setPending(true);
    setError(null);
    try {
      await unsubscribePush();
      setState({ userId, enabled: false });
    } catch {
      setError("알림을 끄지 못했어요. 연결을 확인한 뒤 다시 시도해 주세요.");
    } finally {
      setPending(false);
    }
  }, [userId]);

  return { enabled, checked, pending, error, turnOn, turnOff };
}
