import * as Sentry from "@sentry/nextjs";

import { SENTRY_OPTIONS } from "@/lib/sentry";

// Next 서버(서버 컴포넌트, 서버 액션, api 중계)에서 난 오류를 Sentry 로 보낸다.
// 미들웨어가 없어 edge 런타임은 쓰지 않는다. 무엇을 빼고 보내는지는 lib/sentry.ts.
export function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    Sentry.init(SENTRY_OPTIONS);
  }
}

export const onRequestError = Sentry.captureRequestError;
