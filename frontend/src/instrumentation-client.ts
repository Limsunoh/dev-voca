import * as Sentry from "@sentry/nextjs";

import { SENTRY_OPTIONS } from "@/lib/sentry";

// 폰 화면에서 난 오류를 Sentry 로 보낸다. 무엇을 빼고 보내는지는 lib/sentry.ts.
Sentry.init(SENTRY_OPTIONS);
