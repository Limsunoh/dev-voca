/**
 * node --test 가 프로젝트의 .ts 를 그대로 읽게 해주는 resolve 훅.
 *
 * Next/번들러는 확장자 없는 상대 import("./client")를 알아서 .ts 로 잇지만
 * Node 는 안 한다. 테스트 러너를 새로 붙이지 않으려고(런타임 의존성 3개
 * 규칙) 여기서 최소한만 이어준다. 타입 제거는 Node 가 직접 한다.
 *
 * 쓰는 법: node --experimental-transform-types --import ./tests/ts-resolve.mjs --test tests/*.test.ts
 */
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve as resolvePath } from "node:path";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

/** "./client" -> ".../client.ts" 처럼, 있는 파일이면 확장자를 붙여준다. */
function withExtension(path) {
  for (const suffix of [".ts", ".tsx", "/index.ts", "/index.tsx"]) {
    if (existsSync(path + suffix)) return path + suffix;
  }
  return null;
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    // "server-only" 는 번들러 전용 표시라 Node 에 없다. 빈 모듈로 둔다.
    // 이걸 지우면 서버 전용 모듈을 테스트에서 못 부른다(그 방어선 자체는
    // 아래 server-only.test.ts 가 따로 확인한다).
    if (specifier === "server-only" || specifier === "client-only") {
      return { url: new URL("./empty.mjs", import.meta.url).href, shortCircuit: true };
    }
    // "@/lib/..." 별칭. tsconfig 의 paths 와 같은 규칙.
    if (specifier.startsWith("@/")) {
      const hit = withExtension(resolvePath(SRC, specifier.slice(2)));
      if (hit) return { url: pathToFileURL(hit).href, shortCircuit: true };
    }
    if (specifier.startsWith(".") && context.parentURL?.startsWith("file:")) {
      const base = dirname(fileURLToPath(context.parentURL));
      const hit = withExtension(resolvePath(base, specifier));
      if (hit) return { url: pathToFileURL(hit).href, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
});
