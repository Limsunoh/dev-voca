/**
 * withWrapPoints 의 경계값.
 *
 * 실행: cd frontend && npm test
 *
 * 이 함수는 화면에 나가는 지문·해설 문장을 그대로 받아 <wbr> 만 끼운다.
 * 글자를 하나라도 빼거나 바꾸면 문제 자체가 달라지므로, 가장 먼저 확인할
 * 것은 "wbr 를 걷어내면 원문과 한 글자도 다르지 않다" 이다. 그다음이
 * 어디에 끼우고 어디에 안 끼우나다.
 *
 * 규칙(wrap-points.tsx):
 * - 빈칸 없이 21자 이상인 덩어리에만 넣는다. 짧은 덩어리("src/app.py",
 *   "0.0.0.0:8080")는 줄 끝에서 쪼개지면 더 읽기 어렵다.
 * - 덩어리의 셋째 글자부터 본다. 첫 글자만 줄 끝에 남기지 않는다.
 * - `/` 는 뒤에서 끊는다. 다음 글자가 URL 경로 글자(영숫자 . _ ~ -)일
 *   때만 끊고, "//" 사이와 끝 `/` 다음 닫는 따옴표·괄호 앞에는 안 끊는다.
 * - `.` 는 앞에서 끊는다. 앞이 영숫자이고 뒤가 영문자일 때만.
 * - 소문자 다음 대문자 앞에서 끊는다("Unsupported|Class").
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement, Fragment, isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { withWrapPoints } from "./wrap-points";

const NBSP = "\u00A0";

/** 돌려받은 값을 <p> 안에 그린 HTML(여는·닫는 p 는 뗀다). */
function html(text: string): string {
  const out = renderToStaticMarkup(createElement("p", null, withWrapPoints(text)));
  return out.slice("<p>".length, -"</p>".length);
}

/** 문자열 조각과 wbr 만으로 이뤄졌는지 보고, wbr 를 뺀 글을 돌려준다. */
function strip(node: unknown): string {
  if (typeof node === "string") return node;
  assert.ok(Array.isArray(node), "문자열도 배열도 아닌 값을 돌려줬다");
  return node
    .map((part) => {
      if (typeof part === "string") return part;
      assert.ok(isValidElement(part), "문자열·요소가 아닌 조각이 섞였다");
      assert.equal(part.type, "wbr", "wbr 가 아닌 요소가 섞였다");
      return "";
    })
    .join("");
}

/** 원문에서 wbr 가 들어간 자리(그 앞 글자까지의 길이) 목록. */
function points(text: string): number[] {
  const node = withWrapPoints(text);
  if (typeof node === "string") return [];
  const at: number[] = [];
  let len = 0;
  for (const part of node as unknown[]) {
    if (typeof part === "string") len += part.length;
    else at.push(len);
  }
  return at;
}

/**
 * 규칙을 글자 단위로 다시 적은 것. 구현과 다른 방식(덩어리를 정규식으로
 * 찾지 않고 글자마다 앞뒤 빈칸까지 거리를 잰다)으로 계산해 맞춰 본다.
 */
function expected(text: string): number[] {
  const isSpace = (ch: string | undefined) => ch === undefined || /\s/.test(ch);
  const at: number[] = [];
  for (let k = 1; k < text.length; k++) {
    if (isSpace(text[k])) continue;
    let from = k;
    while (!isSpace(text[from - 1])) from--;
    let to = k;
    while (!isSpace(text[to])) to++;
    if (to - from < 21 || k - from < 2) continue;
    const prev = text[k - 1];
    const here = text[k];
    const next = text[k + 1] ?? "";
    const afterSlash = prev === "/" && /[A-Za-z0-9._~-]/.test(here);
    const beforeDot = here === "." && /[A-Za-z0-9]/.test(prev) && /[A-Za-z]/.test(next);
    const beforeUpper = /[a-z]/.test(prev) && /[A-Z]/.test(here);
    if (afterSlash || beforeDot || beforeUpper) at.push(k);
  }
  return at;
}

/** HTML 에서 wbr 를 걷어낸 글. 렌더러가 글자를 이스케이프하므로 되돌린다. */
function unescape(s: string): string {
  return s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&");
}

const URL = "https://github.com/acme/demo.git";

const SAMPLES = [
  "",
  "a",
  ".",
  "/",
  "//",
  "...",
  "a.",
  "/a",
  "src/app.py",
  "v2.0.0",
  "Bind for 0.0.0.0:8080 failed",
  URL,
  `git clone '${URL}'`,
  "./node_modules/.bin/tsc-and-more-words",
  "home/user/.config/nvim/init.lua",
  "wait...what-is-happening-now",
  "src/components/____/index.tsx",
  "I ran ____ before push.",
  "한글경로/설명/파일이름입니다/추가경로/끝",
  "\u{1F600}/\u{1F600}/\u{1F600}/\u{1F600}/\u{1F600}/\u{1F600}/\u{1F600}/\u{1F600}",
  "a\u{1F600}/b\u{1F600}/c\u{1F600}/d\u{1F600}/e\u{1F600}/f\u{1F600}",
  "'https://example.com/path/'",
  "(see https://example.com/docs/)",
  "src/components/_private/~user/-flag/.env/9x",
  `aaaaaaaaaa/${NBSP}bbbbbbbbbbbbbbbbbb.cc`,
  "a.\tb",
  "a.\nb",
  "<script>alert(1)</script>.x",
  "a & b.c \"q\" 'r' https://example.com/path/to/thing.html",
  "java.lang.UnsupportedClassVersionError: com/example/MyApp",
  "HTTPServerErrorExceptionXYZ",
];

describe("withWrapPoints - 글자가 빠지거나 바뀌지 않는다", () => {
  it("돌려받은 값에서 wbr 를 빼면 원문과 같다", () => {
    for (const text of SAMPLES) {
      assert.equal(strip(withWrapPoints(text)), text, JSON.stringify(text));
    }
  });

  it("그린 HTML 에서 wbr 를 빼면 원문과 같다", () => {
    for (const text of SAMPLES) {
      const drawn = unescape(html(text).replace(/<wbr\/>/g, ""));
      assert.equal(drawn, text, JSON.stringify(text));
    }
  });

  it("샘플의 wbr 자리가 규칙과 같다", () => {
    for (const text of SAMPLES) {
      assert.deepEqual(points(text), expected(text), JSON.stringify(text));
    }
  });

  it("무작위 글 3000개도 원문과 같고 자리가 규칙과 같다", () => {
    // 빈칸을 드물게 두어 21자 넘는 덩어리가 자주 나오게 한다.
    const alphabet = [
      "a", "Z", "q", "1", "9", ".", ".", "/", "/", "_", ":", "-",
      "가", "\u{1F600}", " ", "\n", NBSP,
    ];
    const weights = alphabet.map((ch) => (/\s/.test(ch) ? 1 : 6));
    const total = weights.reduce((a, b) => a + b, 0);
    let seed = 7;
    const rand = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    const pick = () => {
      let r = rand() * total;
      for (let i = 0; i < alphabet.length; i++) {
        r -= weights[i];
        if (r < 0) return alphabet[i];
      }
      return alphabet[0];
    };
    let withPoints = 0;
    for (let n = 0; n < 3000; n++) {
      const len = Math.floor(rand() * 60);
      let text = "";
      for (let i = 0; i < len; i++) text += pick();
      assert.equal(strip(withWrapPoints(text)), text, JSON.stringify(text));
      const want = expected(text);
      assert.deepEqual(points(text), want, JSON.stringify(text));
      if (want.length > 0) withPoints++;
    }
    // 무작위가 늘 "자리 없음" 쪽으로만 떨어지면 이 검사는 아무것도 안 본다.
    assert.ok(withPoints > 500, `자리가 생긴 글이 ${withPoints}개뿐이다`);
  });
});

describe("withWrapPoints - 넣을 자리가 없으면 문자열 그대로", () => {
  const cases = [
    "",
    "a",
    ".",
    "/",
    "//",
    "...",
    "a.",
    "Hi. There.",
    "끝.",
    // 짧은 덩어리는 규칙에 맞는 자리가 있어도 건드리지 않는다.
    "src/app.py",
    "v2.0.0",
    ".git",
    "0.0.0.0:8080",
    "Bind for 0.0.0.0:8080 failed: port is already allocated",
    "I ran ____ before push.",
    // 21자 넘지만 자리 조건에 맞는 글자가 없다.
    "x".repeat(40),
    "18.2.0.18.2.0.18.2.0.1",
    "version-18.2.0-and-more-stuff",
    "wait...what...is...happening",
    // 짧은 camelCase, 숫자 다음 대문자, 대문자끼리, 첫 글자 다음 대문자.
    "getElementById",
    "abc1Defghijklmnopqrstuvw",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "aBcdefghijklmnopqrstuvw",
  ];
  for (const text of cases) {
    it(`${JSON.stringify(text)} 는 문자열로 돌아온다`, () => {
      const node = withWrapPoints(text);
      assert.equal(typeof node, "string");
      assert.equal(node, text);
    });
  }
});

describe("withWrapPoints - 20자·21자 경계", () => {
  it("빈칸 없는 20자는 그대로, 21자부터 넣는다", () => {
    const twenty = "aaaaaaaaaa/bbbbbbbbb";
    const twentyOne = "aaaaaaaaaa/bbbbbbbbbb";
    assert.equal(twenty.length, 20);
    assert.equal(twentyOne.length, 21);
    assert.equal(withWrapPoints(twenty), twenty);
    assert.deepEqual(points(twentyOne), [11]);
  });

  it("앞뒤 빈칸은 덩어리 길이에 안 센다", () => {
    const text = "x aaaaaaaaaa/bbbbbbbbb y";
    assert.equal(withWrapPoints(text), text);
  });

  it("NBSP·탭·줄바꿈도 덩어리를 가른다", () => {
    for (const sep of [NBSP, "\t", "\n", " "]) {
      const text = `aaaaa/aaaa${sep}bbbbbbbbbb/bbbbbbbbb`;
      assert.equal(withWrapPoints(text), text, JSON.stringify(sep));
    }
  });

  it("짧은 덩어리와 긴 덩어리가 섞이면 긴 쪽에만", () => {
    const text = `src/app.py ${URL} v2.0.0`;
    const at = points(text);
    assert.ok(at.length > 0);
    assert.ok(at.every((k) => k > "src/app.py ".length && k < text.length - " v2.0.0".length), String(at));
  });
});

describe("withWrapPoints - 넣는 자리", () => {
  it("URL: '//' 사이는 안 끊고, / 뒤·. 앞에서 끊는다", () => {
    assert.deepEqual(points(URL), [8, 14, 19, 24, 28]);
    assert.equal(html(URL), "https://<wbr/>github<wbr/>.com/<wbr/>acme/<wbr/>demo<wbr/>.git");
  });

  it("점은 앞에서 끊는다 - 줄 끝에 점이 남지 않는다", () => {
    const out = html("example.com/path/to/resource");
    assert.equal(out, "example<wbr/>.com/<wbr/>path/<wbr/>to/<wbr/>resource");
    assert.doesNotMatch(out, /\.<wbr\/>/);
  });

  it("숫자 사이 점에는 안 넣는다(버전·IP)", () => {
    assert.equal(
      html("tcp://0.0.0.0:8080/health/check"),
      "tcp://<wbr/>0.0.0.0:8080/<wbr/>health/<wbr/>check",
    );
    assert.equal(html("react-dom@18.2.0/cjs/react.js"), "react-dom@18.2.0/<wbr/>cjs/<wbr/>react<wbr/>.js");
  });

  it("숫자 뒤 영문자 앞의 점에는 넣는다(앞 글자는 영숫자면 된다)", () => {
    assert.deepEqual(points("file-version-2.txt-backup"), [14]);
  });

  it("앞 점: 앞 글자가 영숫자가 아니면 점 앞에 안 넣는다", () => {
    // "..." 의 셋째 점은 뒤가 영문자지만 앞이 점이다.
    assert.equal(withWrapPoints("wait...what-is-happening-now"), "wait...what-is-happening-now");
    assert.equal(withWrapPoints("some_thing-_.hidden-file-name"), "some_thing-_.hidden-file-name");
  });

  it("소문자 다음 대문자 앞에서 끊는다(자바 예외 이름)", () => {
    assert.equal(
      html("java.lang.UnsupportedClassVersionError:"),
      "java<wbr/>.lang<wbr/>.Unsupported<wbr/>Class<wbr/>Version<wbr/>Error:",
    );
  });

  it("대문자 다음 대문자·대문자 다음 소문자 앞에는 안 넣는다", () => {
    // HTTPServer 의 S 는 앞이 대문자라 안 끊는다.
    assert.deepEqual(points("HTTPServerErrorExceptionXYZ"), [10, 15, 24]);
  });

  it("/ 다음 . 은 빗금 규칙으로 빗금 뒤에서 끊는다", () => {
    assert.equal(
      html("home/user/.config/nvim/init.lua"),
      "home/<wbr/>user/<wbr/>.config/<wbr/>nvim/<wbr/>init<wbr/>.lua",
    );
  });

  it("덩어리 첫 글자 뒤에는 안 넣는다(/ 로 시작, 한 글자 뒤 점)", () => {
    assert.deepEqual(points("/home/user/projects/app"), [6, 11, 20]);
    assert.equal(withWrapPoints("a.bcdefghijklmnopqrstuv"), "a.bcdefghijklmnopqrstuv");
    // 둘째 글자 뒤(셋째 글자 앞)는 된다.
    assert.deepEqual(points("ab.cdefghijklmnopqrstuv"), [2]);
    assert.deepEqual(points("x/y/zzzzzzzzzzzzzzzzzzzz"), [2, 4]);
  });

  it("덩어리 끝의 / 와 문장 끝 마침표에는 안 넣는다", () => {
    assert.deepEqual(points(`${URL}/`), [8, 14, 19, 24, 28]);
    assert.deepEqual(points(`${URL}.`), [8, 14, 19, 24, 28]);
  });

  it("/ 다음이 URL 경로 글자(영숫자 . _ ~ -)일 때만 끊는다", () => {
    // _ 는 목록에 있어 "_private" 앞에서 끊는다.
    assert.equal(
      html("src/components/_private/~user/-flag/.env/9x"),
      "src/<wbr/>components/<wbr/>_private/<wbr/>~user/<wbr/>-flag/<wbr/>.env/<wbr/>9x",
    );
    // 끝 / 다음 닫는 따옴표·괄호 앞에는 안 넣는다.
    assert.equal(
      html("'https://example.com/path/'"),
      "&#x27;https://<wbr/>example<wbr/>.com/<wbr/>path/&#x27;",
    );
    assert.equal(
      html("(see https://example.com/docs/)"),
      "(see https://<wbr/>example<wbr/>.com/<wbr/>docs/)",
    );
    // 한글·이모지·콜론·따옴표 앞에는 안 넣는다.
    for (const text of [
      "한글경로/설명/파일이름입니다/추가경로/끝",
      "aaaaaaaaaa/:bbbbbbbbbbbbbbb",
      "aaaaaaaaaa/\"bbbbbbbbbbbbbbb",
      "aaaaaaaaaa/@bbbbbbbbbbbbbbb",
    ]) {
      assert.equal(withWrapPoints(text), text, text);
    }
  });

  it("빈칸 표시 '____' 는 쪼개지 않는다", () => {
    assert.equal(
      html("src/components/____/index.tsx"),
      "src/<wbr/>components/<wbr/>____/<wbr/>index<wbr/>.tsx",
    );
    assert.equal(withWrapPoints("fatal: ____ unrelated histories"), "fatal: ____ unrelated histories");
  });

  it("이모지 옆에서도 서로게이트 짝을 가르지 않는다", () => {
    // / 다음이 이모지면 안 넣으므로, 영문자를 끼워 자리를 만든다.
    const emoji = "a\u{1F600}/b\u{1F600}/c\u{1F600}/d\u{1F600}/e\u{1F600}/f\u{1F600}";
    assert.equal(withWrapPoints("\u{1F600}/".repeat(12)), "\u{1F600}/".repeat(12));
    const node = withWrapPoints(emoji) as unknown[];
    assert.ok(Array.isArray(node));
    assert.equal(node.filter(isValidElement).length, 5);
    for (const part of node) {
      if (typeof part !== "string" || part.length === 0) continue;
      assert.doesNotMatch(part, /^[\uDC00-\uDFFF]|[\uD800-\uDBFF]$/, JSON.stringify(part));
    }
  });

  it("HTML 로 보이는 글은 이스케이프된 채로 나간다", () => {
    const out = html("<script>alert(1)</script>.x");
    assert.doesNotMatch(out, /<script>/);
    assert.equal(out, "&lt;script&gt;alert(1)&lt;/<wbr/>script&gt;.x");
  });

  it("wbr 의 key 는 겹치지 않는다(React 경고 없이 그린다)", () => {
    const node = withWrapPoints(`${URL} ${URL}`) as unknown[];
    const keys = node.filter(isValidElement).map((el) => el.key);
    assert.equal(keys.length, 10);
    assert.equal(new Set(keys).size, keys.length);
    const errors: unknown[] = [];
    const real = console.error;
    console.error = (...args: unknown[]) => errors.push(args);
    try {
      renderToStaticMarkup(createElement(Fragment, null, node as ReactNode));
    } finally {
      console.error = real;
    }
    assert.deepEqual(errors, []);
  });
});
