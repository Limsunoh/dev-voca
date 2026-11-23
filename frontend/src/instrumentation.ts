import * as Sentry from "@sentry/nextjs";

import { SENTRY_OPTIONS } from "@/lib/sentry";

// Next 서버(서버 컴포넌트, 서버 액션, api 중계)에서 난 오류를 Sentry 로 보낸다.
// edge 런타임은 쓰지 않는다. proxy.ts 도 Node.js 런타임에서 돈다(Next 16 기본값).
// 무엇을 빼고 보내는지는 lib/sentry.ts.
export function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    Sentry.init(SENTRY_OPTIONS);
  }
}

export const onRequestError = Sentry.captureRequestError;
