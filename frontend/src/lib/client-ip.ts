import "server-only";

import { headers } from "next/headers";

/**
 * 가입·로그인 요청과, 로그인하지 않고 부르는 문제풀기·순위표·소리내어 읽기 요청에
 * 싣는 머리. 백엔드가 그 요청들을 접속 IP 로 센다(backend/apps/accounts/throttles.py
 * 의 client_ident). 로그인한 요청에는 lib/api/client.ts 의 guestHeaders 가 버린다.
 *
 * 브라우저는 백엔드를 직접 부르지 않고 이 Next 서버가 대신 불러서, 백엔드가 보는
 * 접속 주소는 늘 Vercel 이다. 그래서 여기서 실제 IP 를 싣는다. x-forwarded-for 는
 * Vercel 이 접속자 IP 로 덮어써 두므로 사용자가 지어 보낼 수 없다(맨 앞이 접속자).
 *
 * 둘이 나눠 가진 비밀값(RELAY_SECRET)도 싣는다. 백엔드 주소는 공개돼 있어 아무나 이
 * 머리를 지어 바로 보낼 수 있으므로, 백엔드는 비밀값이 맞는 요청만 Next 에서 온 것으로
 * 보고 나머지는 한 통으로 센다.
 *
 * RELAY_SECRET 이 없으면(로컬 개발) 아무것도 싣지 않는다.
 */
export async function clientIpHeaders(): Promise<Record<string, string>> {
  const secret = process.env.RELAY_SECRET;
  if (!secret) return {};

  const relay = { "X-Next-Relay": secret };
  const ip = ((await headers()).get("x-forwarded-for") ?? "").split(",")[0]?.trim();
  if (!ip) return relay;

  return { ...relay, "X-Next-Client-IP": ip };
}
