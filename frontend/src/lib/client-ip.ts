import "server-only";

import { headers } from "next/headers";

/**
 * 접속 IP 를 백엔드에 싣기 시작하는 날(한국 시간). 처리방침 v3 가 "로그인·가입 시도 때
 * 접속 IP 가 Railway 로 넘어간다" 를 싣고 시행하는 날이다. 그 전에는 IP 를 보내지 않는다.
 * 백엔드의 IP_COUNT_FROM(backend/apps/accounts/throttles.py)과 처리방침 v3 시행일
 * (2026-11-19, 14절에 글자로 적음)이 이 값과 같은지는 client-ip.test.mts 가 본다.
 * PRIVACY_CHANGE.effective 는 v4 시행일(11-20)이라 견주지 않는다.
 *
 * ponytail: 날짜로 켜는 문이다. 시행일이 지나면 이 상수와 아래 날짜 비교를 지운다
 * (백엔드 IP_COUNT_FROM 의 주석에 지울 목록이 있다).
 */
export const IP_FROM = "2026-11-19";

/** 한국 시간 날짜("2026-11-19"). 서버(Vercel)의 시각대와 상관없이 같게 센다. */
function koreaDate(now: number): string {
  return new Date(now + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

/**
 * 가입·로그인 요청에 싣는 머리. 백엔드의 가입·로그인 제한이 접속 IP 로 센다
 * (backend/apps/accounts/throttles.py).
 *
 * 브라우저는 백엔드를 직접 부르지 않고 이 Next 서버가 대신 불러서, 백엔드가 보는
 * 접속 주소는 늘 Vercel 이다. 그래서 여기서 실제 IP 를 싣는다. x-forwarded-for 는
 * Vercel 이 접속자 IP 로 덮어써 두므로 사용자가 지어 보낼 수 없다(맨 앞이 접속자).
 *
 * 둘이 나눠 가진 비밀값(RELAY_SECRET)은 날짜와 상관없이 늘 싣는다. 백엔드 주소는 공개돼
 * 있어 아무나 이 머리를 지어 바로 보낼 수 있으므로, 백엔드는 비밀값이 맞는 요청만 Next 에서
 * 온 것으로 보고 나머지는 한 통으로 센다.
 *
 * RELAY_SECRET 이 없으면(로컬 개발) 아무것도 싣지 않는다.
 */
export async function clientIpHeaders(now = Date.now()): Promise<Record<string, string>> {
  const secret = process.env.RELAY_SECRET;
  if (!secret) return {};

  const relay = { "X-Next-Relay": secret };
  if (koreaDate(now) < IP_FROM) return relay;

  const ip = ((await headers()).get("x-forwarded-for") ?? "").split(",")[0]?.trim();
  if (!ip) return relay;

  return { ...relay, "X-Next-Client-IP": ip };
}
