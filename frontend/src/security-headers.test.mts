/**
 * 화면 응답에 붙는 보안 헤더 설정을 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 마이크를 막으면 말하기 연습이 조용히 죽으므로 값까지 고정한다.
 */
import assert from "node:assert/strict";
import { it } from "node:test";

const nextConfig = (await import("../next.config")).default;

it("모든 경로에 보안 헤더를 붙이고 프레임워크 이름을 숨긴다", async () => {
  const rules = await nextConfig.headers!();

  assert.equal(rules.length, 1);
  assert.equal(rules[0].source, "/:path*");
  assert.deepEqual(
    Object.fromEntries(rules[0].headers.map((h) => [h.key, h.value])),
    {
      "X-Frame-Options": "DENY",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "Permissions-Policy": "microphone=(self)",
    },
  );
  assert.equal(nextConfig.poweredByHeader, false);
});
