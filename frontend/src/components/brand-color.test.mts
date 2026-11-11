/**
 * 강조색을 코랄에서 로고 갈색으로 옮긴 뒤(2026-11-11)의 쓰임새 규칙을 지킨다.
 *
 * 실행: cd frontend && npm test
 *
 * 갈색(--brand)은 누르는 곳과 "지금 여기", 코랄은 틀림·오류·되돌리기 어려운
 * 동작·급한 남은 시간이다. 값 하나만 되돌려도 화면은 "색이 조금 다른" 정도라
 * 눈으로는 놓친다. 그래서 토큰이 서로 어떻게 이어지는지와, 앱 바깥에서 따로
 * 칠하는 끊김 안내 화면(offline.html)이 globals.css 를 따라오는지를 본다.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { contrast, token } from "./contrast-helpers.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..");
const PUBLIC = join(HERE, "../../public");

/** 체크아웃 설정(autocrlf)에 따라 줄끝이 달라도 같은 값이 나오게 맞춘다. */
const readText = (path: string) => readFileSync(path, "utf8").replace(/\r\n/g, "\n");

function sources(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) sources(path, out);
    else if (/\.tsx?$/.test(entry.name) && !/\.test\./.test(entry.name)) out.push(path);
  }
  return out;
}

/** 패턴이 걸린 파일과 줄. 실패 메시지에 어디인지 바로 보이게 한다. */
function grepSources(pattern: RegExp): string[] {
  const hits: string[] = [];
  for (const file of sources(SRC)) {
    readText(file)
      .split("\n")
      .forEach((line, i) => {
        if (pattern.test(line)) hits.push(`${relative(SRC, file)}:${i + 1}`);
      });
  }
  return hits;
}

describe("강조 토큰의 연결", () => {
  it("갈색 버튼의 두께와 포커스 링은 --brand-deep 이다", () => {
    // 코랄로 남으면 갈색 버튼 아래에 붉은 띠가 붙고, 포커스가 오류처럼 읽힌다.
    // token() 은 값 전체가 var() 일 때만 풀어서, 섞인 값은 글자 그대로 본다.
    assert.equal(token("--lift-button"), "0 4px 0 var(--brand-deep)");
    assert.equal(token("--focus"), token("--brand-deep"));
  });

  it("갈색과 진한 갈색은 코랄 계열과 다른 값이다", () => {
    for (const brand of ["--brand", "--brand-deep", "--brand-soft"]) {
      for (const coral of ["--coral", "--coral-deep", "--wrong", "--wrong-deep", "--wrong-soft"]) {
        assert.notEqual(token(brand).toLowerCase(), token(coral).toLowerCase(), `${brand} = ${coral}`);
      }
    }
  });

  it("포커스 링은 갈색 버튼과 크림 사이에서도 보인다(테두리 기준 3:1)", () => {
    // outline-offset 2px 의 링은 크림 위에 그려진다. 버튼과 같은 색으로 가면
    // 대비는 크림 쪽이 지킨다.
    assert.ok(contrast(token("--focus"), token("--background")) >= 3);
  });

  it("--brand-orange 는 축하 효과에만 쓴다", () => {
    // 크림 위 2.2:1 이라 글자·테두리·버튼에 쓰면 안 보인다.
    assert.ok(contrast(token("--brand-orange"), token("--background")) < 3);
    assert.equal(token("--confetti-1"), token("--brand-orange"));
    assert.deepEqual(grepSources(/--brand-orange/), []);
  });
});

describe("코랄의 쓰임새", () => {
  it("코랄로 채운 면이 없다 - 채움은 누르는 곳(갈색)의 표시다", () => {
    // 오답은 테두리, 오류 상자는 --wrong-soft 바탕에 진한 코랄 글자다.
    // 코랄로 채운 버튼이 다시 생기면 주된 동작과 오류가 한 색이 된다.
    // 조건식(urgent ? "var(--coral)" : ...)으로 칠한 것도 잡는다. 예외는 90초
    // 한 판의 급한 남은 시간 막대 하나다(RoundBoard).
    const hits = grepSources(/background:[^,}]*"var\(--(coral|coral-deep|wrong|wrong-deep)\)"/);
    for (const hit of hits) assert.match(hit, /^components[\\/]RoundBoard\.tsx:/, hit);
    assert.ok(hits.length <= 1, hits.join(", "));
  });

  it("밝은 코랄(--coral)은 급한 남은 시간에만 직접 쓴다", () => {
    // 크림 위 3.15:1 이라 24px 이상 굵은 숫자에서만 글자 기준을 넘는다.
    // 나머지 코랄 글자는 --coral-deep(또는 --wrong-deep)이다.
    const hits = grepSources(/var\(--coral\)/);
    assert.ok(hits.length > 0, "급한 남은 시간 표시를 못 찾았다");
    for (const hit of hits) assert.match(hit, /^components[\\/]RoundBoard\.tsx:/, hit);
  });

  it("지운 토큰(--coral-soft, --coral-soft-text)을 부르는 곳이 없다", () => {
    // 정의가 없는 var() 는 에러 없이 빈 값이 되어 바탕·글자가 조용히 사라진다.
    assert.deepEqual(grepSources(/--coral-soft/), []);
    assert.doesNotMatch(readText(join(SRC, "app", "globals.css")), /--coral-soft/);
  });
});

describe("끊김 안내 화면(offline.html)", () => {
  const html = readText(join(PUBLIC, "offline.html")).toLowerCase();
  const button = /button\s*\{([^}]*)\}/.exec(html)?.[1] ?? "";
  const focus = /button:focus-visible\s*\{([^}]*)\}/.exec(html)?.[1] ?? "";

  it("다시 시도 버튼은 globals.css 의 --brand 바탕에 흰 글자다", () => {
    assert.ok(button, "button 규칙을 못 찾았다");
    assert.match(button, new RegExp(`background:\\s*${token("--brand").toLowerCase()}\\s*;`));
    assert.match(button, /color:\s*#ffffff\s*;/);
  });

  it("포커스 테두리는 globals.css 의 --focus 와 같다", () => {
    assert.ok(focus, "button:focus-visible 규칙을 못 찾았다");
    assert.match(focus, new RegExp(`outline:\\s*2px solid ${token("--focus").toLowerCase()}`));
  });

  it("코랄을 쓰지 않는다", () => {
    for (const coral of ["--coral", "--coral-deep"]) {
      assert.ok(!html.includes(token(coral).toLowerCase()), `${coral} 가 남아 있다`);
    }
  });

  it("내용을 바꿨으면 sw.js 의 CACHE 도 올렸다", () => {
    // 브라우저는 sw.js 가 바뀔 때만 다시 설치하고 안내 화면도 그때만 새로
    // 받는다. CACHE 를 안 올리면 이미 설치된 폰에는 옛 화면이 남는다.
    //
    // offline.html 을 고쳐서 여기가 빨개지면: sw.js 의 CACHE 숫자를 하나
    // 올리고, 아래 표에 새 이름과 새 지문을 적는다.
    const SEEN: Record<string, string> = {
      "offline-v2": "89a5709b06506326630957a9d4326c63cda70c89",
      "offline-v3": "5ea0676f3eca8178638f3b8717f268b579b02e00",
    };
    const sw = readText(join(PUBLIC, "sw.js"));
    const cache = /const CACHE = "([^"]+)";/.exec(sw)?.[1];
    assert.ok(cache, "sw.js 에서 CACHE 를 못 찾았다");
    const digest = createHash("sha1").update(readText(join(PUBLIC, "offline.html"))).digest("hex");
    assert.equal(SEEN[cache], digest, `CACHE=${cache}, offline.html 지문=${digest}`);
  });
});
