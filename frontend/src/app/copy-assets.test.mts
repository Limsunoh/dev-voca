/**
 * 고지 문구와 정적 자산 검증.
 *
 * 실행: cd frontend && npm test
 *
 *     마이크 안내   음성이 가는 곳을 한 회사로 단정하지 않는다
 *     한 판 메타    순위표에 오르려면 로그인이 필요하다고 말한다
 *     안 쓰는 자산  Next 시작 템플릿의 SVG 5개가 다시 생기거나 참조되지 않는다.
 *                   로고 전 임시 아이콘 icon.svg 도 참조되지 않는다
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const THIS_FILE = fileURLToPath(import.meta.url);
const HERE = dirname(THIS_FILE);
const SRC = join(HERE, "..");
const PUBLIC = join(HERE, "../../public");

const REMOVED_SVGS = ["file.svg", "globe.svg", "next.svg", "vercel.svg", "window.svg"];

const read = (path: string) => readFileSync(path, "utf8");

/** MicGate 의 고지 문단에서 화면에 나오는 글자만. 줄바꿈으로 끊긴 말을 잇는다. */
function micNotice(): string {
  const source = read(join(SRC, "components/MicGate.tsx")).replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
  const at = source.indexOf("copy.showPrivacy &&");
  assert.notEqual(at, -1, "고지 문단을 못 찾았다");
  const open = source.indexOf("<p", at);
  const close = source.indexOf("</p>", open);
  const paragraph = source.slice(open, close);
  return paragraph.slice(paragraph.lastIndexOf(">") + 1).replace(/\s+/g, " ").trim();
}

function roundDescription(): string {
  const source = read(join(HERE, "test/round/page.tsx"));
  const found = source.match(/export const metadata[\s\S]*?description:\s*"([^"]*)"/);
  assert.ok(found, "메타 설명을 못 찾았다");
  return found[1];
}

function sourceFiles(dir: string): string[] {
  const found: string[] = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) found.push(...sourceFiles(path));
    else if ([".ts", ".tsx", ".mts", ".css", ".json", ".svg"].includes(extname(name))) found.push(path);
  }
  return found;
}

describe("마이크 안내", () => {
  it("브라우저 제공 업체를 거친다고 말한다", () => {
    assert.match(micNotice(), /브라우저 제공 업체/);
  });

  it("구글은 크롬의 예시로만 나온다", () => {
    assert.doesNotMatch(micNotice().replace("크롬은 구글 등", ""), /구글/);
  });

  it("devvoca 서버에는 글자만 온다는 안내가 남아 있다", () => {
    assert.match(micNotice(), /devvoca 서버에는 바뀐 글자만 오고 목소리는 저장하지 않습니다/);
  });
});

describe("한 판 메타 설명", () => {
  it("로그인해야 순위표에 오른다고 말한다", () => {
    assert.match(roundDescription(), /로그인하면/);
  });
});

describe("지운 자산", () => {
  for (const name of REMOVED_SVGS) {
    it(`public/${name} 가 없다`, () => {
      assert.equal(existsSync(join(PUBLIC, name)), false);
    });
  }

  it("src 어디서도 지운 파일을 참조하지 않는다", () => {
    const pattern = /(?<![\w-])(?:file|globe|next|vercel|window|icon)\.svg\b|favicon\.ico/;
    // 테스트 파일은 "없어야 한다" 를 확인하려고 지운 이름을 일부러 적는다.
    const files = sourceFiles(SRC).filter((path) => !/\.test\.m?ts$/.test(path));
    assert.ok(files.length > 100, `훑은 파일이 너무 적다: ${files.length}`);

    const offenders = files.filter((path) => pattern.test(read(path)));
    assert.deepEqual(offenders, []);
  });
});
