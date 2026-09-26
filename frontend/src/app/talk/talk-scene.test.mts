/**
 * 일상영어(/talk)의 상황(?scene=) 축을 본다. 중계와 페이지 둘 다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약은 넷이다.
 *   1. 중계(POST /api/talk, action:"start")는 아는 상황 다섯 개만 백엔드
 *      쿼리에 싣는다. 모르는 값(대문자·쉼표 두 값·배열·객체·숫자·
 *      `__proto__`·긴 문자열)은 아예 안 싣는다 - 브라우저가 보낸 아무
 *      문자열이 백엔드 주소로 흘러가면 안 된다.
 *   2. 상황은 난이도·exclude 와 같이 실린다. 하나 때문에 다른 것이 빠지면
 *      안 된다.
 *   3. 백엔드가 "이 상황은 다 봤습니다" 404 를 주면 중계가 그 문구와 상태를
 *      그대로 돌려준다. 문구를 바꾸면 사용자는 전체를 다 본 줄 안다.
 *   4. 페이지는 개발 용어(?kind=dev)에서 상황 탭을 안 그리고, 주소에 scene 이
 *      남아 있어도 판(TalkBoard)에 넘기지 않는다. 세 줄의 링크는 서로의 값을
 *      들고 다닌다.
 *
 * 백엔드는 부르지 않는다. 전역 fetch 를 대역으로 바꿔 중계가 부른 주소를
 * 잡는다(sort-page.test.mts 와 같은 방식). 세션은 "server-only" 라 Next 밖
 * 에서 import 하면 터져서 대역으로 바꾼다(kind-page.test.mts).
 *
 * 기대 주소는 routes 로 다시 계산하지 않고 문자열로 적는다. 같은 함수로
 * 기대값을 만들면 그 함수가 틀려도 테스트가 같이 초록불이다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("@/lib/session", {
  namedExports: {
    getToken: async () => null,
    // 토큰이 없으니 그대로 게스트로 부른다(실제 구현과 같다).
    withTokenOrGuest: async <T,>(
      token: string | null,
      call: (token?: string) => Promise<T>,
    ) => ({ value: await call(token ?? undefined), token }),
  },
});

type LinkProps = { href: string; children?: ReactNode };
mock.module("next/link", {
  defaultExport: (props: LinkProps & Record<string, unknown>) =>
    createElement(
      "a",
      { href: props.href, "aria-current": props["aria-current"] },
      props.children,
    ),
});

// ---- 백엔드 대역 ----------------------------------------------------------

/** 중계가 부른 백엔드 주소들. */
let calls: URL[] = [];
/** 다음 응답. 기본은 쇼핑 문장 하나. */
let reply: { status: number; body: unknown } = { status: 200, body: {} };

const prompt = {
  token: "t",
  id: 7,
  kind: "phrase",
  term: "how much is this",
  pronunciation: "/x/",
  reading: "x",
  meaning: "얼마예요",
  difficulty: 1,
  difficulty_label: "쉬움",
  scene: "shopping",
  scene_label: "쇼핑·주문",
};

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request) => {
  calls.push(new URL(String(input)));
  return new Response(JSON.stringify(reply.body), {
    status: reply.status,
    headers: { "Content-Type": "application/json" },
  });
}) as typeof fetch;
after(() => {
  globalThis.fetch = realFetch;
});

const { POST } = await import("../api/talk/route");
const TalkPage = (await import("./page")).default;
const { TalkPromptCard } = await import("@/components/TalkPrompt");

beforeEach(() => {
  calls = [];
  reply = { status: 200, body: prompt };
});

/** 중계에 start 를 보내고, 백엔드로 간 쿼리와 중계 응답을 돌려준다. */
async function start(body: Record<string, unknown>) {
  const res = await POST(
    new Request("http://x/api/talk", {
      method: "POST",
      body: JSON.stringify({ action: "start", ...body }),
    }),
  );
  assert.equal(calls.length, 1, "백엔드를 한 번 불러야 한다");
  return { res, query: calls[0].searchParams, path: calls[0].pathname };
}

// ---------------------------------------------------------------------------
// 중계
// ---------------------------------------------------------------------------

const SCENES = ["greeting", "shopping", "asking", "trouble", "smalltalk"];

describe("중계: 상황을 백엔드 쿼리에 싣는다", () => {
  for (const scene of SCENES) {
    it(`아는 상황 ${scene} 은 그대로 싣는다`, async () => {
      const { res, query, path } = await start({ scene });
      assert.equal(res.status, 200);
      assert.match(path, /\/talk\/question\/$/);
      assert.deepEqual(query.getAll("scene"), [scene]);
    });
  }

  it("상황·난이도·exclude 를 같이 싣는다", async () => {
    const { query } = await start({ scene: "trouble", level: 3, exclude: [4, 9] });
    assert.equal(query.get("scene"), "trouble");
    assert.equal(query.get("level"), "3");
    assert.equal(query.get("exclude"), "4,9");
    assert.equal(query.get("kind"), null);
  });

  it("상황을 안 보내면 scene 을 안 싣는다", async () => {
    const { query } = await start({});
    assert.equal(query.has("scene"), false);
  });

  const bad: [string, unknown][] = [
    ["빈 문자열", ""],
    ["대문자", "SHOPPING"],
    ["앞 공백", " shopping"],
    ["뒤 NUL", "shopping\u0000"],
    ["쉼표 두 값", "shopping,asking"],
    ["배열", ["shopping"]],
    ["객체", { scene: "shopping" }],
    ["숫자", 1],
    ["true", true],
    ["null", null],
    ["__proto__", "__proto__"],
    ["constructor", "constructor"],
    ["한글 이름", "쇼핑·주문"],
    ["필드 조회 문법", "scene__in"],
    ["주소 끼워넣기", "shopping&level=3"],
    ["2만 자", "x".repeat(20000)],
  ];
  for (const [name, scene] of bad) {
    it(`모르는 값(${name})은 싣지 않고 전체로 떨어진다`, async () => {
      const { res, query } = await start({ scene, level: 2 });
      assert.equal(res.status, 200);
      assert.equal(query.has("scene"), false, query.toString());
      // 끼워넣은 값이 다른 파라미터를 덮지 않는다.
      assert.deepEqual(query.getAll("level"), ["2"]);
    });
  }

  it("JSON 에 __proto__ 키로 scene 을 숨겨 보내도 싣지 않는다", async () => {
    const res = await POST(
      new Request("http://x/api/talk", {
        method: "POST",
        body: '{"action":"start","__proto__":{"scene":"shopping"}}',
      }),
    );
    assert.equal(res.status, 200);
    assert.equal(calls[0].searchParams.has("scene"), false);
  });

  it("백엔드의 '이 상황은 다 봤습니다' 404 를 문구·상태 그대로 돌려준다", async () => {
    const detail = "이 상황은 다 봤습니다. 상황을 바꾸거나 잠시 뒤 다시 해보세요.";
    reply = { status: 404, body: { detail } };
    const { res } = await start({ scene: "greeting", exclude: [1, 2] });
    assert.equal(res.status, 404);
    assert.deepEqual(await res.json(), { detail });
  });

  it("받은 scene·scene_label 을 그대로 내려준다", async () => {
    const { res } = await start({ scene: "shopping" });
    const body = await res.json();
    assert.equal(body.scene, "shopping");
    assert.equal(body.scene_label, "쇼핑·주문");
  });
});

// ---------------------------------------------------------------------------
// 페이지
// ---------------------------------------------------------------------------

type El = { type: unknown; props: Record<string, unknown> };

/** 페이지가 돌려준 트리에서 이름이 name 인 컴포넌트를 전부 찾는다. */
function findAll(node: unknown, name: string, out: El[] = []): El[] {
  if (Array.isArray(node)) {
    for (const child of node) findAll(child, name, out);
  } else if (node && typeof node === "object" && "props" in node) {
    const el = node as El;
    if (typeof el.type === "function" && el.type.name === name) out.push(el);
    findAll(el.props.children, name, out);
  }
  return out;
}

async function visit(search: Record<string, string | string[]>) {
  const tree = await TalkPage({ searchParams: Promise.resolve(search) });
  const html = renderToStaticMarkup(tree as ReturnType<typeof createElement>);
  // 탭 줄마다 (링크 글자 -> href), 켜진 것은 글자 뒤에 * 를 붙인다.
  const rows: Record<string, string[]> = {};
  for (const [, label, inner] of html.matchAll(
    /<nav aria-label="([^"]+)"[^>]*>([\s\S]*?)<\/nav>/g,
  )) {
    rows[label] = [...inner.matchAll(/<a([^>]*)>(.*?)<\/a>/g)].map(
      ([, attrs, text]) =>
        `${text}${attrs.includes('aria-current="page"') ? "*" : ""}=${
          /href="([^"]*)"/.exec(attrs)![1].replace(/&amp;/g, "&")
        }`,
    );
  }
  const board = findAll(tree, "TalkBoard")[0];
  return { tree, rows, board, html };
}

describe("페이지: 상황 탭과 주소", () => {
  it("상황을 고르면 세 줄이 서로의 값을 들고 다닌다", async () => {
    const { rows, board } = await visit({ level: "3", scene: "trouble" });
    assert.deepEqual(rows["읽을 갈래"], [
      "일상 표현*=/talk?level=3&scene=trouble",
      // 개발 용어에는 상황이 없어서 이 링크만 scene 을 뺀다.
      "개발 용어=/talk?kind=dev&level=3",
    ]);
    assert.deepEqual(rows["난이도"], [
      "전체=/talk?scene=trouble",
      "쉬움=/talk?level=1&scene=trouble",
      "보통=/talk?level=2&scene=trouble",
      "어려움*=/talk?level=3&scene=trouble",
    ]);
    assert.deepEqual(rows["상황"], [
      "전체=/talk?level=3",
      "인사·소개=/talk?level=3&scene=greeting",
      "쇼핑·주문=/talk?level=3&scene=shopping",
      "묻기·길찾기=/talk?level=3&scene=asking",
      "곤란할 때*=/talk?level=3&scene=trouble",
      "가벼운 대화=/talk?level=3&scene=smalltalk",
    ]);
    assert.equal(board.props.scene, "trouble");
    assert.equal(board.props.level, 3);
  });

  for (const raw of ["bogus", "SHOPPING", "__proto__", "x".repeat(5000), ""]) {
    it(`모르는 상황 ${JSON.stringify(raw.slice(0, 12))} 은 전체로 본다`, async () => {
      const { rows, board } = await visit({ scene: raw });
      assert.equal(rows["상황"][0], "전체*=/talk");
      assert.equal(rows["상황"].filter((r) => r.includes("*")).length, 1);
      assert.equal(board.props.scene, "");
      assert.equal(rows["읽을 갈래"][0], "일상 표현*=/talk");
    });
  }

  it("scene 이 두 번 오면 첫 값 하나만 쓴다", async () => {
    const { rows, board } = await visit({ scene: ["shopping", "asking"] });
    assert.equal(board.props.scene, "shopping");
    assert.deepEqual(
      rows["상황"].filter((r) => r.includes("*")),
      ["쇼핑·주문*=/talk?scene=shopping"],
    );
  });

  const devSearches: Record<string, string>[] = [
    { kind: "dev", scene: "shopping" },
    { kind: "dev", level: "2", scene: "asking" },
  ];
  for (const search of devSearches) {
    it(`개발 용어(${JSON.stringify(search)})는 상황 탭이 없고 판에도 안 넘긴다`, async () => {
      const { rows, board, html } = await visit(search);
      assert.equal(rows["상황"], undefined);
      assert.equal(board.props.scene, "");
      assert.equal(board.props.kind, "dev");
      assert.doesNotMatch(html, /scene=/);
      // 판의 key 에도 scene 이 안 섞인다 - 섞이면 보이지 않는 조건 때문에
      // 판이 새로 만들어진다.
      const key = String((board as unknown as { key: string }).key);
      assert.match(key, /dev/);
      assert.doesNotMatch(key, /asking|shopping/);
    });
  }

  it("상황을 바꾸면 판의 key 가 바뀐다 - 옛 문장과 exclude 가 따라오지 않는다", async () => {
    const keyOf = async (search: Record<string, string>) =>
      String(((await visit(search)).board as unknown as { key: string }).key);
    const keys = new Set([
      await keyOf({}),
      ...(await Promise.all(SCENES.map((scene) => keyOf({ scene })))),
    ]);
    assert.equal(keys.size, SCENES.length + 1, [...keys].join(" "));
  });
});

// ---------------------------------------------------------------------------
// 카드 배지
// ---------------------------------------------------------------------------

describe("카드: 상황 배지", () => {
  const card = (patch: Partial<typeof prompt>) =>
    renderToStaticMarkup(
      createElement(TalkPromptCard, { prompt: { ...prompt, ...patch } as never }),
    );

  it("상황 이름이 있으면 난이도 옆에 그린다", () => {
    const html = card({});
    assert.match(html, />쉬움<\/span>/);
    assert.match(html, />쇼핑·주문<\/span>/);
  });

  it("상황이 비면(개발 용어·상황 없는 표현) 빈 알약을 그리지 않는다", () => {
    const html = card({ scene: "", scene_label: "" });
    assert.match(html, />쉬움<\/span>/);
    // 난이도 배지 하나만 남는다.
    assert.equal(html.match(/rounded-full/g)?.length, 1, html);
  });
});
