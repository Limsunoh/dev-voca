/**
 * 서비스 이름 DeVoca 의 표기가 화면마다 같은지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * brand-rename.test.mts 는 옛 이름(devvoca, dev-voca)이 남지 않았는지 본다. 여기서는
 * 새 이름을 잘못 적은 것(Devoca, DEVOCA, De Voca, deVoca)을 잡는다. 옛 이름 검사로는
 * 안 걸린다.
 *
 * 계약:
 *   - 주석을 뺀 소스와 public 의 글(offline.html, sw.js)에서 대소문자를 무시하고 찾은
 *     서비스 이름은 모두 정확히 "DeVoca" 다.
 *   - 화면 제목(metadata title)을 정하는 파일은 모두 제목 끝이 "DeVoca" 다. 가운뎃점
 *     뒤에 붙는 이름도 DeVoca 다.
 *   - <BrandName /> 은 줄이 안 갈리는 DeVoca 한 덩어리로 그려진다.
 *   - 설치 이름(manifest name, short_name)은 DeVoca 다.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..");
const PUBLIC = join(SRC, "../public");

// 낱말 사이에 공백·하이픈·밑줄·점이 끼어도 서비스 이름으로 본다. 옛 이름
// devvoca, dev-voca 는 "de" 바로 뒤가 "voca" 가 아니라 여기에 안 걸린다.
// 앞뒤에 영문자가 붙은 것(codevocab, made vocal)은 이름이 아니다.
const ANY_CASE_NAME = /(?<![a-z])de[\s\-_.]?voca(?![a-z])/gi;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(tsx?|mts)$/.test(name) && !/\.test\./.test(name) ? [path] : [];
  });
}

/** 주석을 지운 소스. 문자열과 JSX 글자는 남는다. */
function withoutComments(source: string): string {
  return source
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/(^|\s)\/\/.*$/gm, "$1");
}

/** 정확히 DeVoca 가 아닌 표기를 "파일: 표기" 로 모은다. */
function misspelled(files: string[]): string[] {
  return files.flatMap((path) => {
    const text = withoutComments(readFileSync(path, "utf8")).replaceAll("dev-voca.vercel.app", "");
    return [...text.matchAll(ANY_CASE_NAME)]
      .map((m) => m[0])
      .filter((found) => found !== "DeVoca")
      .map((found) => `${relative(SRC, path)}: ${found}`);
  });
}

describe("서비스 이름 DeVoca 표기", () => {
  it("소스에 나오는 서비스 이름은 모두 정확히 DeVoca 다", () => {
    const files = sourceFiles(SRC);
    assert.ok(files.length > 50, `훑은 파일이 너무 적다: ${files.length}`);
    assert.deepEqual(misspelled(files), []);
  });

  it("public 의 끊김 안내와 service worker 에도 잘못 적은 이름이 없다", () => {
    const files = ["offline.html", "sw.js"].map((name) => join(PUBLIC, name));
    assert.deepEqual(misspelled(files), []);
    assert.match(readFileSync(files[0], "utf8"), /<title>[^<]*· DeVoca<\/title>/);
  });

  it("화면 제목을 정하는 파일은 모두 제목이 DeVoca 로 끝난다", () => {
    const metadataFiles = sourceFiles(join(SRC, "app")).filter((path) =>
      /export (const metadata|async function generateMetadata|function generateMetadata)/.test(
        readFileSync(path, "utf8"),
      ),
    );
    assert.ok(metadataFiles.length > 15, `제목을 정하는 파일이 너무 적다: ${metadataFiles.length}`);

    const problems = metadataFiles.flatMap((path) => {
      const titles = [...withoutComments(readFileSync(path, "utf8")).matchAll(/title:\s*(["`])([^"`]*)\1/g)].map(
        (m) => m[2],
      );
      const rel = relative(SRC, path);
      const out: string[] = [];
      if (!titles.some((t) => t.endsWith("DeVoca"))) out.push(`${rel}: DeVoca 로 끝나는 제목이 없다`);
      // 가운뎃점 뒤에 붙는 것은 언제나 서비스 이름이다.
      for (const t of titles) {
        if (t.includes(" · ") && !t.endsWith(" · DeVoca")) out.push(`${rel}: ${t}`);
      }
      return out;
    });
    assert.deepEqual(problems, []);
  });

  it("BrandName 은 줄이 안 갈리는 DeVoca 한 덩어리로 그려진다", async () => {
    const { BrandName } = await import("../components/BrandName");
    assert.equal(
      renderToStaticMarkup(createElement(BrandName)),
      '<span class="whitespace-nowrap">DeVoca</span>',
    );
  });

  it("설치 이름은 DeVoca 다", async () => {
    const { default: manifest } = await import("./manifest");
    const data = manifest();
    assert.equal(data.name, "DeVoca");
    assert.equal(data.short_name, "DeVoca");
  });
});
