/**
 * 서비스 이름을 화면 문단에 쓸 때 <BrandName /> 을 쓰는지 검증.
 *
 * 실행: cd frontend && npm test
 *
 * 문단 안의 이름을 BrandName.tsx 한 곳에 모으려는 것이다. 문단에 "DeVoca" 를
 * 글자로 쓰면 다음에 이름을 바꿀 때 그 자리를 놓친다. 따옴표 안의 값(탭 제목, alt)은
 * 대개 문단이 아니다. 그래서 주석과 따옴표 안을 지운 뒤 남은 "DeVoca" 를 찾는다.
 * 본문에 {"DeVoca"} 로 쓴 것도 잡는다. 처음에는 옛 이름 dev-voca 가 하이픈 뒤에서
 * 줄이 갈려서 만든 검사다.
 *
 * 못 잡는 것: 문자열로 들고 있다가 본문에 그리는 값(섹션 제목, 문구 객체, LegalDoc 의
 * title). 지금 그런 곳은 계정 삭제 안내의 큰 제목 하나다.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..");

function tsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return tsxFiles(path);
    return name.endsWith(".tsx") && name !== "BrandName.tsx" ? [path] : [];
  });
}

// 본문 중괄호 안에 문자열로 쓴 이름: {"DeVoca"}, {`DeVoca 서버`}
const STRING_IN_JSX = /\{\s*["'`][^"'`\n]*DeVoca/;

/** 주석과 문자열을 지운 소스. JSX 글자만 남는다. */
function jsxText(source: string): string {
  return source
    .replace(/\{\/\*[\s\S]*?\*\/\}|\/\*[\s\S]*?\*\/|^\s*\/\/.*$/gm, "")
    .replace(/"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`/g, "");
}

describe("서비스 이름", () => {
  it("문단 안에 DeVoca 를 글자로 쓰지 않고 <BrandName /> 을 쓴다", () => {
    const files = tsxFiles(SRC);
    assert.ok(files.length > 50, `훑은 파일이 너무 적다: ${files.length}`);

    const offenders = files
      .filter((path) => {
        const source = readFileSync(path, "utf8");
        return STRING_IN_JSX.test(source) || jsxText(source).includes("DeVoca");
      })
      .map((path) => relative(SRC, path));
    assert.deepEqual(offenders, []);
  });

  it("BrandName 은 줄바꿈을 막는다", () => {
    const source = readFileSync(join(HERE, "BrandName.tsx"), "utf8");
    assert.match(source, /className="whitespace-nowrap">DeVoca</);
  });
});
