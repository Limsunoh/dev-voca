/**
 * 끊김 안내 service worker 와 그 등록을 실제로 돌려 본다.
 *
 * 실행: cd frontend && npm test
 *
 * manifest.test.mts 는 sw.js 를 글자로 읽어 모양만 본다. 여기서는 sw.js 를 가짜
 * self·caches·fetch 위에서 실행해 이벤트마다 무엇을 하는지 본다.
 *
 * 계약:
 *   - 등록은 운영 빌드에서만, /sw.js 하나만. 등록이 실패해도 화면이 죽지 않는다.
 *   - install 에서 offline.html 을 캐시에 넣고 바로 대기를 건너뛴다.
 *   - activate 에서 지금 캐시 이름이 아닌 것만 지우고, 다 지운 뒤에 화면을 넘겨받는다.
 *   - 화면 이동(navigate) 요청만 가로챈다. 네트워크가 되면 그 응답을 그대로,
 *     안 되면 캐시한 offline.html 을 준다. API·그림·POST(fetch) 는 손대지 않는다.
 *
 * react 대역은 refresh-on-back.test.mts 와 같은 방식이다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { afterEach, describe, it, mock } from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const SW_SOURCE = readFileSync(join(HERE, "../../public/sw.js"), "utf8");

// ---- ServiceWorkerRegister -------------------------------------------------

const require = createRequire(import.meta.url);
const realReact = require("react") as typeof import("react");

let effects: Array<() => void> = [];

mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useEffect: (fn: () => void) => void effects.push(fn),
  },
});

const { ServiceWorkerRegister } = await import("./ServiceWorkerRegister");

const originalEnv = process.env.NODE_ENV;
const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");

function setNavigator(value: unknown) {
  Object.defineProperty(globalThis, "navigator", { value, configurable: true, writable: true });
}

/** 컴포넌트를 한 번 그리고 모인 effect 를 돌린다. 그린 결과를 돌려준다. */
function mountAndRunEffects() {
  effects = [];
  const out = ServiceWorkerRegister();
  for (const fn of effects) fn();
  return out;
}

describe("ServiceWorkerRegister", () => {
  afterEach(() => {
    (process.env as Record<string, string | undefined>).NODE_ENV = originalEnv;
    if (originalNavigator) Object.defineProperty(globalThis, "navigator", originalNavigator);
  });

  it("화면에는 아무것도 그리지 않는다", () => {
    setNavigator({});
    assert.equal(mountAndRunEffects(), null);
  });

  for (const env of ["development", "test", undefined]) {
    it(`NODE_ENV=${env} 이면 등록하지 않는다`, () => {
      const register = mock.fn(() => Promise.resolve({}));
      setNavigator({ serviceWorker: { register } });
      const vars = process.env as Record<string, string | undefined>;
      if (env === undefined) delete vars.NODE_ENV;
      else vars.NODE_ENV = env;
      mountAndRunEffects();
      assert.equal(register.mock.callCount(), 0);
    });
  }

  it("운영 빌드에서는 /sw.js 를 한 번 등록한다", () => {
    const register = mock.fn(() => Promise.resolve({}));
    setNavigator({ serviceWorker: { register } });
    (process.env as Record<string, string>).NODE_ENV = "production";
    mountAndRunEffects();
    assert.equal(register.mock.callCount(), 1);
    assert.deepEqual(register.mock.calls[0].arguments, ["/sw.js"]);
  });

  it("service worker 를 모르는 브라우저에서도 터지지 않는다", () => {
    setNavigator({});
    (process.env as Record<string, string>).NODE_ENV = "production";
    assert.doesNotThrow(() => mountAndRunEffects());
  });

  it("등록이 실패해도 처리되지 않은 거부가 남지 않는다", async () => {
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown) => unhandled.push(reason);
    process.on("unhandledRejection", onUnhandled);
    try {
      const register = mock.fn(() => Promise.reject(new Error("SecurityError")));
      setNavigator({ serviceWorker: { register } });
      (process.env as Record<string, string>).NODE_ENV = "production";
      mountAndRunEffects();
      await new Promise((r) => setTimeout(r, 20));
      assert.equal(register.mock.callCount(), 1);
      assert.deepEqual(unhandled, []);
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });
});

// ---- sw.js -----------------------------------------------------------------

type Listener = (event: FakeEvent) => void;
type FakeEvent = {
  request?: Request;
  preloadResponse?: Promise<Response | undefined>;
  waitUntil: (p: Promise<unknown>) => void;
  respondWith: (p: Promise<Response> | Response) => void;
};

/** sw.js 를 새 가짜 전역 위에서 한 번 실행한다. */
function loadWorker(opts: {
  network: (req: Request) => Promise<Response>;
  cacheNames?: string[];
  /** 없으면 navigation preload 를 모르는 브라우저처럼 둔다. */
  navigationPreload?: { enable: () => Promise<void> };
}) {
  const listeners: Record<string, Listener> = {};
  const stored = new Map<string, Map<string, Response>>();
  for (const n of opts.cacheNames ?? []) stored.set(n, new Map());
  const log: string[] = [];

  const caches = {
    open: async (name: string) => {
      if (!stored.has(name)) stored.set(name, new Map());
      const bucket = stored.get(name)!;
      return {
        add: async (request: string | { url: string; cache?: string }) => {
          const url = typeof request === "string" ? request : request.url;
          const mode = typeof request === "string" ? "default" : request.cache;
          log.push(`add ${name} ${url} cache=${mode}`);
          bucket.set(url, new Response("<h1>offline</h1>", { status: 200 }));
        },
      };
    },
    keys: async () => [...stored.keys()],
    delete: async (name: string) => {
      log.push(`delete ${name}`);
      return stored.delete(name);
    },
    match: async (url: string) => {
      for (const bucket of stored.values()) if (bucket.has(url)) return bucket.get(url)!.clone();
      return undefined;
    },
  };

  const fetchFn = mock.fn(opts.network);
  const self = {
    addEventListener: (type: string, fn: Listener) => void (listeners[type] = fn),
    skipWaiting: mock.fn(() => Promise.resolve()),
    registration: { navigationPreload: opts.navigationPreload },
    clients: {
      claim: mock.fn(async () => {
        log.push("claim");
      }),
    },
  };

  /** 서비스 워커 안의 Request 는 상대 주소를 받는다. 주소와 cache 옵션만 흉내 낸다. */
  class SwRequest {
    url: string;
    cache: string;
    constructor(url: string, init: { cache?: string } = {}) {
      this.url = url;
      this.cache = init.cache ?? "default";
    }
  }

  vm.runInNewContext(SW_SOURCE, { self, caches, fetch: fetchFn, Response, Request: SwRequest, Promise });

  /** 이벤트를 하나 보내고 waitUntil·respondWith 로 받은 것을 돌려준다. */
  async function dispatch(type: string, request?: Request, preloadResponse?: Promise<Response | undefined>) {
    let waited: Promise<unknown> | undefined;
    let responded: Promise<Response> | Response | undefined;
    let respondCalls = 0;
    listeners[type]({
      request,
      preloadResponse,
      waitUntil: (p) => void (waited = p),
      respondWith: (p) => {
        respondCalls++;
        responded = p;
      },
    });
    if (waited) await waited;
    return { response: responded ? await responded : undefined, respondCalls };
  }

  return { listeners, stored, log, fetchFn, self, dispatch };
}

const ORIGIN = "https://devvoca.example";

/** 브라우저가 만든 것처럼 mode 를 지정한 요청. Node 의 Request 는 navigate 를 못 만든다. */
function req(path: string, mode: string, init: RequestInit = {}) {
  const r = new Request(ORIGIN + path, init);
  Object.defineProperty(r, "mode", { value: mode });
  return r;
}

const offline = () => Promise.reject(new TypeError("Failed to fetch"));

describe("sw.js 설치와 정리", () => {
  it("install 에서 offline.html 을 HTTP 캐시를 거치지 않고 offline-v2 캐시에 넣고 대기를 건너뛴다", async () => {
    const w = loadWorker({ network: offline });
    await w.dispatch("install");
    assert.deepEqual(w.log, ["add offline-v2 /offline.html cache=reload"]);
    assert.equal(w.self.skipWaiting.mock.callCount(), 1);
  });

  it("activate 는 옛 안내 화면 캐시만 지우고 다른 기능의 캐시는 남긴 뒤에 화면을 넘겨받는다", async () => {
    const w = loadWorker({
      network: offline,
      cacheNames: ["offline-v1", "offline-v2", "something-else"],
    });
    await w.dispatch("activate");
    assert.deepEqual([...w.stored.keys()], ["offline-v2", "something-else"]);
    // 지우기가 다 끝난 다음에 claim 해야 한다.
    assert.equal(w.log.at(-1), "claim");
    assert.deepEqual(w.log.filter((l) => l.startsWith("delete")), ["delete offline-v1"]);
  });

  it("activate 는 navigation preload 를 켠다", async () => {
    const enable = mock.fn(async () => {});
    const w = loadWorker({ network: offline, cacheNames: ["offline-v2"], navigationPreload: { enable } });
    await w.dispatch("activate");
    assert.equal(enable.mock.callCount(), 1);
  });

  it("activate 는 지울 캐시가 없어도 화면을 넘겨받는다", async () => {
    const w = loadWorker({ network: offline, cacheNames: ["offline-v2"] });
    await w.dispatch("activate");
    assert.deepEqual(w.log, ["claim"]);
  });
});

describe("sw.js 요청 처리", () => {
  it("미리 보낸 화면 요청(preload)의 응답이 있으면 그것을 주고 다시 받지 않는다", async () => {
    const page = new Response("preloaded", { status: 200 });
    const w = loadWorker({ network: async () => new Response("second fetch") });
    await w.dispatch("install");
    const { response } = await w.dispatch("fetch", req("/learn/words", "navigate"), Promise.resolve(page));
    assert.equal(response, page);
    assert.equal(w.fetchFn.mock.callCount(), 0);
  });

  it("미리 보낸 요청이 끊겨 실패해도 안내 화면을 준다", async () => {
    const w = loadWorker({ network: offline });
    await w.dispatch("install");
    const { response } = await w.dispatch(
      "fetch",
      req("/learn/words", "navigate"),
      Promise.reject(new TypeError("Failed to fetch")),
    );
    assert.equal(response?.status, 200);
    assert.equal(await response?.text(), "<h1>offline</h1>");
  });

  it("화면 이동이 성공하면 네트워크 응답을 그대로 준다", async () => {
    const page = new Response("real page", { status: 200 });
    const w = loadWorker({ network: async () => page });
    await w.dispatch("install");
    const { response } = await w.dispatch("fetch", req("/learn/words", "navigate"));
    assert.equal(response, page);
  });

  it("화면 이동의 404·500 도 안내 화면으로 바꾸지 않는다", async () => {
    // 서버가 답을 준 것은 끊긴 게 아니다. not-found 화면이 가려지면 안 된다.
    for (const status of [404, 500, 503]) {
      const page = new Response("server said", { status });
      const w = loadWorker({ network: async () => page });
      await w.dispatch("install");
      const { response } = await w.dispatch("fetch", req("/nope", "navigate"));
      assert.equal(response, page, `status ${status}`);
    }
  });

  it("화면 이동이 네트워크에서 실패하면 캐시한 안내 화면을 200 으로 준다", async () => {
    const w = loadWorker({ network: offline });
    await w.dispatch("install");
    const { response } = await w.dispatch("fetch", req("/profile", "navigate"));
    assert.ok(response);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), "<h1>offline</h1>");
  });

  it("안내 화면은 여러 번 끊겨도 매번 온전히 나온다", async () => {
    // 캐시 응답 본문을 한 번 읽고 나면 다시 못 읽는 실수를 잡는다.
    const w = loadWorker({ network: offline });
    await w.dispatch("install");
    for (const path of ["/a", "/b", "/c"]) {
      const { response } = await w.dispatch("fetch", req(path, "navigate"));
      assert.equal(await response!.text(), "<h1>offline</h1>", path);
    }
  });

  it("안내 화면이 캐시에 없으면 네트워크 오류로 돌려준다(빈 200 이 아니다)", async () => {
    const w = loadWorker({ network: offline });
    // install 을 건너뛰어 캐시가 빈 상태
    const { response } = await w.dispatch("fetch", req("/learn", "navigate"));
    assert.ok(response);
    assert.equal(response.type, "error");
    assert.equal(response.status, 0);
  });

  it("화면 이동 요청을 그대로 네트워크에 넘긴다(주소를 바꾸지 않는다)", async () => {
    const w = loadWorker({ network: async () => new Response("ok") });
    const navigation = req("/learn/words?q=api", "navigate");
    await w.dispatch("fetch", navigation);
    assert.equal(w.fetchFn.mock.callCount(), 1);
    assert.equal(w.fetchFn.mock.calls[0].arguments[0], navigation);
  });

  const notNavigations: Array<[string, Request]> = [
    ["API GET", req("/api/words?page=2", "cors")],
    ["API POST", req("/api/quiz/grade", "cors", { method: "POST", body: "{}" })],
    ["서버 액션 POST", req("/login", "cors", { method: "POST", body: "x" })],
    ["그림", req("/icons/icon-192.png", "no-cors")],
    ["스크립트", req("/_next/static/chunks/main.js", "no-cors")],
    ["같은 출처 fetch", req("/manifest.webmanifest", "same-origin")],
    ["RSC 이동 데이터", req("/learn?_rsc=abc", "cors")],
  ];
  for (const [name, request] of notNavigations) {
    it(`가로채지 않는다: ${name}`, async () => {
      const w = loadWorker({ network: offline });
      await w.dispatch("install");
      const { respondCalls } = await w.dispatch("fetch", request);
      assert.equal(respondCalls, 0);
      assert.equal(w.fetchFn.mock.callCount(), 0);
    });
  }
});

describe("ServiceWorkerRegister 를 화면 전체에 단다", () => {
  it("layout.tsx 가 body 안에서 ServiceWorkerRegister 를 그린다", () => {
    const layout = readFileSync(join(HERE, "../app/layout.tsx"), "utf8");
    assert.match(layout, /import \{ ServiceWorkerRegister \} from "@\/components\/ServiceWorkerRegister";/);
    const body = layout.slice(layout.indexOf("<body"), layout.indexOf("</body>"));
    assert.match(body, /<ServiceWorkerRegister \/>/);
  });
});
