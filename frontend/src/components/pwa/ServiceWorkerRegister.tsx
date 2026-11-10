"use client";

import { useEffect } from "react";
import { API_BASE_URL } from "@/lib/api/client";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
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
