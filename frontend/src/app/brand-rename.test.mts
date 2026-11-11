/**
 * 서비스 이름을 바꾼 뒤에도 지켜야 할 것. devvoca -> dev-voca -> DeVoca(2026-11-11).
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 화면에 나가는 글(JSX 글자, 제목·설명 문자열, alt)에 옛 표기 devvoca, dev-voca 가
 *     없다. 웹 주소 dev-voca.vercel.app 은 앱이 묶여 있어 그대로다.
 *     주석과 쿠키 이름(devvoca_token 등)은 일부러 옛 이름 그대로다.
 *   - 쿠키 이름은 바꾸지 않았다. 바꾸면 이미 로그인한 회원이 전부 로그아웃된다.
 *   - 처리방침이 적은 쿠키 이름과 코드가 실제로 쓰는 쿠키 이름이 같다.
 *     한쪽만 고치면 처리방침이 없는 쿠키를 설명하게 된다.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { describe, it, mock } from "node:test";
import { fileURLToPath } from "node:url";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// 여기서 볼 것은 글자뿐이다. next/link 는 브라우저 라우터를 기대한다.
mock.module("next/link", {
  defaultExport: (props: { href: string; children: ReactNode }) =>
    createElement("a", { href: props.href }, props.children),
});

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..");
const read = (path: string) => readFileSync(join(SRC, path), "utf8");

// 쿠키 이름 꼴. 이 꼴은 옛 이름이 남아 있어야 맞다.
const COOKIE = /devvoca_[a-z_]+/g;
// 쿠키 이름도 웹 주소도 아닌 옛 표기. 대소문자를 바꾼 DevVoca, Dev-Voca 도 잡는다.
const OLD_NAME = /devvoca(?!_)|dev-voca(?!\.vercel\.app)/i;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(name) && !/\.test\./.test(name) ? [path] : [];
  });
}

/** 주석을 지운 소스. 문자열과 JSX 글자는 남는다. */
function withoutComments(source: string): string {
  return source
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|\s)\/\/.*$/gm, "$1");
}

/** 코드가 쓰는 쿠키 이름. 상수로 정의한 자리에서 읽는다. */
function cookiesInCode(): Set<string> {
  const files = ["lib/session.ts", "app/api/auth/google/route.ts"];
  return new Set(files.flatMap((file) => withoutComments(read(file)).match(COOKIE) ?? []));
}

const { default: PrivacyPage } = await import("./privacy/page");
const { default: TermsPage } = await import("./terms/page");
const { default: DeleteAccountPage } = await import("./delete-account/page");

const pages = {
  privacy: renderToStaticMarkup(createElement(PrivacyPage)),
  terms: renderToStaticMarkup(createElement(TermsPage)),
  "delete-account": renderToStaticMarkup(createElement(DeleteAccountPage)),
};

describe("서비스 이름 바꾸기", () => {
  it("화면에 나가는 글에 옛 표기 devvoca, dev-voca 가 없다", () => {
    const files = sourceFiles(SRC);
    assert.ok(files.length > 50, `훑은 파일이 너무 적다: ${files.length}`);

    const offenders = files.flatMap((path) =>
      withoutComments(readFileSync(path, "utf8"))
        .split("\n")
        .filter((line) => OLD_NAME.test(line))
        .map((line) => `${relative(SRC, path)}: ${line.trim()}`),
    );
    assert.deepEqual(offenders, []);
  });

  for (const [name, html] of Object.entries(pages)) {
    it(`${name}: 쿠키 이름을 적은 <code> 밖에는 옛 표기가 없고 DeVoca 가 있다`, () => {
      const outsideCode = html.replace(/<code>devvoca_[a-z_]+<\/code>/g, "");
      assert.doesNotMatch(outsideCode, OLD_NAME);
      assert.match(html, /DeVoca/);
    });
  }

  it("쿠키 이름은 옛 이름 그대로다", () => {
    assert.deepEqual(
      [...cookiesInCode()].sort(),
      [
        "devvoca_daily_length",
        "devvoca_guest",
        "devvoca_oauth_consent",
        "devvoca_oauth_next",
        "devvoca_oauth_state",
        "devvoca_token",
      ],
    );
  });

  it("처리방침에 적힌 쿠키와 코드가 쓰는 쿠키가 같다", () => {
    const listed = new Set(
      [...pages.privacy.matchAll(/<code>(devvoca_[a-z_]+)<\/code>/g)].map((m) => m[1]),
    );
    assert.deepEqual([...listed].sort(), [...cookiesInCode()].sort());
  });
});
