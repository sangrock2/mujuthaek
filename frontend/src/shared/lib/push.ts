import { api } from "@/shared/lib/api/client";
import { endpoints } from "@/shared/lib/api/endpoints";

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";
let pendingPush: Promise<void> = Promise.resolve();

/** 등록·해제·로그아웃을 같은 브라우저에서 직렬화해 해제 직후 지연된 PUT이 되살리지 못하게 해요. */
function withPushLock<T>(run: () => Promise<T>): Promise<T> {
  const result = pendingPush.then(async (): Promise<T> => {
    if (typeof navigator !== "undefined" && navigator.locks) {
      return await navigator.locks.request(
        "mujuthaek-push-subscription",
        { signal: AbortSignal.timeout(20000) },
        run,
      );
    }
    return run();
  });
  pendingPush = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return Uint8Array.from(rawData, (char) => char.charCodeAt(0));
}

function sameKey(a: ArrayBuffer | null, b: Uint8Array) {
  if (!a || a.byteLength !== b.length) return false;
  const x = new Uint8Array(a);
  return x.every((v, i) => v === b[i]);
}

export function isPushSupported() {
  return (
    typeof navigator !== "undefined" &&
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export async function getPushSubscription() {
  if (!isPushSupported()) return null;
  // ready는 등록에 실패한 브라우저에서 끝나지 않아요. 로그아웃은 현재 등록이 없으면 바로 계속해요.
  const registration = await navigator.serviceWorker.getRegistration();
  return registration?.pushManager.getSubscription() ?? null;
}

async function registerSubscription(subscription: PushSubscription) {
  await api.put(
    endpoints.pushSubscriptions,
    {
      ...subscription.toJSON(),
      userAgent: navigator.userAgent,
    },
    { signal: AbortSignal.timeout(10000) },
  );
}

async function removeBrowserSubscription(subscription: PushSubscription) {
  if (!(await subscription.unsubscribe()) && (await getPushSubscription())) {
    throw new Error("이 브라우저의 알림을 끄지 못했어요. 다시 시도해 주세요.");
  }
}

/** 로그인·계정 변경 때 기존 구독을 현재 계정에 맞춰요. 실패하면 이전 계정 알림이 남지 않게 브라우저 구독도 꺼요. */
export function syncExistingPushSubscription(isCurrent: () => boolean = () => true) {
  return withPushLock(async () => {
    const subscription = await getPushSubscription();
    if (!subscription || !isCurrent()) return false;
    try {
      await registerSubscription(subscription);
      return isCurrent();
    } catch (error) {
      await removeBrowserSubscription(subscription);
      throw error;
    }
  });
}

/** 로그인하지 않았거나 약관 동의 전인 계정에는 이전 사람의 브라우저 알림을 남기지 않아요. */
export function stopBrowserPushSubscription(isCurrent: () => boolean = () => true) {
  return withPushLock(async () => {
    const subscription = await getPushSubscription();
    if (subscription && isCurrent()) await removeBrowserSubscription(subscription);
  });
}

/** 공개키: 설정 값이 있으면 그것, 없으면 백엔드에서 받아요 (백엔드에 키가 없으면 503) */
async function publicKey() {
  if (VAPID_PUBLIC_KEY) return VAPID_PUBLIC_KEY;
  const { publicKey } = await api.get<{ publicKey: string }>(endpoints.pushPublicKey);
  return publicKey;
}

export async function subscribePush() {
  // 허용 창은 버튼을 누른 바로 그때 띄워야 브라우저가 막지 않아요 (다른 요청을 먼저 기다리지 않기)
  const permission = await Notification.requestPermission();
  if (permission !== "granted")
    throw new Error(
      "브라우저에서 알림이 허용되지 않았어요. 주소창 왼쪽 자물쇠에서 알림을 허용해 주세요.",
    );

  return withPushLock(async () => {
    const key = await publicKey().catch(() => "");
    if (!key) throw new Error("알림 서버 설정(공개키)을 받지 못했어요. 잠시 뒤 다시 해 주세요.");
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration)
      throw new Error("알림 준비를 마치지 못했어요. 화면을 새로 열고 다시 시도해 주세요.");
    const old = await registration.pushManager.getSubscription();
    if (old && !sameKey(old.options.applicationServerKey, urlBase64ToUint8Array(key))) {
      await removeBrowserSubscription(old);
    }
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key),
    });
    try {
      await registerSubscription(subscription);
    } catch (error) {
      await removeBrowserSubscription(subscription);
      throw error;
    }
    return subscription;
  });
}

async function unsubscribeCurrentPush() {
  const subscription = await getPushSubscription();
  if (!subscription) return;
  await api.delete(endpoints.pushSubscriptions, {
    body: { endpoint: subscription.endpoint },
    signal: AbortSignal.timeout(10000),
  });
  await removeBrowserSubscription(subscription);
}

export function unsubscribePush() {
  return withPushLock(unsubscribeCurrentPush);
}

/** 현재 기기만 해제한 뒤 세션을 끝내요. 해제 실패 때는 로그아웃 성공으로 표시하지 않아요. */
export function logoutWithPushCleanup(logout: () => Promise<void>) {
  return withPushLock(async () => {
    await unsubscribeCurrentPush();
    await logout();
  });
}
