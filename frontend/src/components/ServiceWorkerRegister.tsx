"use client";

import { useEffect } from "react";

/**
 * public/sw.js 를 등록한다. 화면에는 아무것도 그리지 않는다.
 *
 * 운영 빌드에서만 등록한다. 개발 서버에서 등록하면 브라우저에 남아, 서버를 끈
 * 동안 화면 대신 "인터넷 연결 없음" 이 떠서 헷갈린다.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // 등록이 실패해도 화면은 그대로 돈다. 끊겼을 때 안내 화면만 못 띄운다.
    });
  }, []);
  return null;
}
