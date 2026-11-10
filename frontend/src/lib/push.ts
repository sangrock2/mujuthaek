import { api } from "@/lib/api/client";
import { endpoints } from "@/lib/api/endpoints";

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";

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
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function getPushSubscription() {
  const registration = await navigator.serviceWorker.ready;
  return registration.pushManager.getSubscription();
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

  const key = await publicKey().catch(() => "");
  if (!key) throw new Error("알림 서버 설정(공개키)을 받지 못했어요. 잠시 뒤 다시 해 주세요.");

  const registration = await navigator.serviceWorker.ready;
  // 예전에 다른 키로 받은 구독이 남아 있으면 새 키로 받을 수 없어서 먼저 풀어요
  const old = await registration.pushManager.getSubscription();
  if (old && !sameKey(old.options.applicationServerKey, urlBase64ToUint8Array(key))) {
    await old.unsubscribe();
  }
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(key),
  });
  // 기기 목록에 보여 줄 이름으로 브라우저 정보를 함께 보내요 (백엔드가 200자로 잘라요)
  await api.put(endpoints.pushSubscriptions, {
    ...subscription.toJSON(),
    userAgent: navigator.userAgent,
  });
  return subscription;
}

export async function unsubscribePush() {
  const subscription = await getPushSubscription();
  if (!subscription) return;
  await api.delete(endpoints.pushSubscriptions, {
    body: { endpoint: subscription.endpoint },
  });
  await subscription.unsubscribe();
}
