"use client";

import { useEffect } from "react";
import { API_BASE_URL } from "@/shared/lib/api/client";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    // 개발 번들은 파일명에 내용 해시가 없어요. 캐시 우선 워커가 예전 코드를 돌려주지 않게 해요.
    if (process.env.NODE_ENV !== "production") {
      void navigator.serviceWorker.getRegistrations().then((registrations) =>
        Promise.all(
          registrations
            .filter((registration) => {
              const script = registration.active?.scriptURL;
              return script && new URL(script).pathname === "/sw.js";
            })
            .map((registration) => registration.unregister()),
        ),
      );
      return;
    }
    navigator.serviceWorker
      // 서비스 워커가 알림을 봤는지·눌렀는지 백엔드에 알릴 수 있게 주소를 넘겨요
      .register(`/sw.js?api=${encodeURIComponent(API_BASE_URL)}`, {
        scope: "/",
        updateViaCache: "none",
      })
      .catch((error) => console.error("서비스 워커 등록 실패", error));
  }, []);

  return null;
}
