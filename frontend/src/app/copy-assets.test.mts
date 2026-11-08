/**
 * 고지 문구와 정적 자산 검증.
 *
 * 실행: cd frontend && npm test
 *
 *     마이크 안내   음성이 가는 곳을 한 회사로 단정하지 않는다
 *     한 판 메타    순위표에 오르려면 로그인이 필요하다고 말한다
 *     아이콘        favicon.ico 대신 도형만 쓴 icon.svg. 글꼴과 외부 파일에
 *                   기대지 않아야 어디서든 같게 보인다
 *     안 쓰는 자산  Next 시작 템플릿의 SVG 5개가 다시 생기거나 참조되지 않는다
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

/** XML 주석을 뺀 아이콘 원문. 주석 속 글자로 오탐하지 않게 한다. */
function iconSource(): string {
  return read(join(HERE, "icon.svg")).replace(/<!--[\s\S]*?-->/g, "");
}

type Tag = { name: string; attrs: Record<string, string> };

/** 짝이 맞는 XML 인지 보고 태그 목록을 돌려준다. 노드에 XML 파서가 없어 직접 센다. */
function parseTags(source: string): Tag[] {
  const pattern = /<(\/?)([A-Za-z][\w:-]*)((?:\s+[\w:-]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*(\/?)>/g;
  const tags: Tag[] = [];
  const open: string[] = [];
  let roots = 0;

  const rest = source.replace(pattern, (_all, closing, name, attrs, selfClosing) => {
    if (closing) {
      assert.equal(open.pop(), name, `닫는 태그 ${name} 의 짝이 안 맞는다`);
      return "";
    }
    if (open.length === 0) roots += 1;
    const parsed: Record<string, string> = {};
    for (const [, key, double, single] of attrs.matchAll(/([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g)) {
      parsed[key] = double ?? single;
    }
    tags.push({ name, attrs: parsed });
    if (!selfClosing) open.push(name);
    return "";
  });

  assert.equal(open.length, 0, `안 닫힌 태그: ${open.join(", ")}`);
  assert.equal(roots, 1, "루트 요소가 하나가 아니다");
  assert.equal(rest.trim(), "", `태그로 해석되지 않는 글자가 남았다: ${rest.trim()}`);
  return tags;
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

describe("앱 아이콘", () => {
  it("favicon.ico 가 없다", () => {
    assert.equal(existsSync(join(HERE, "favicon.ico")), false);
  });

  it("icon.svg 가 짝이 맞는 SVG 다", () => {
    const [root] = parseTags(iconSource());
    assert.equal(root.name, "svg");
    assert.equal(root.attrs.xmlns, "http://www.w3.org/2000/svg");
    const box = (root.attrs.viewBox ?? "").trim().split(/\s+/).map(Number);
    assert.equal(box.length, 4, "viewBox 가 없거나 네 값이 아니다");
    assert.ok(box.every(Number.isFinite), "viewBox 가 숫자가 아니다");
    assert.ok(box[2] > 0 && box[3] > 0, "viewBox 크기가 0 이다");
  });

  it("글꼴에 기대는 요소가 없다", () => {
    const tags = parseTags(iconSource());
    for (const tag of tags) {
      assert.doesNotMatch(tag.name, /^(text|tspan|textPath|foreignObject|style)$/i);
      assert.equal(tag.attrs["font-family"], undefined, "font-family 가 있다");
    }
  });

  it("외부를 참조하지 않는다", () => {
    const tags = parseTags(iconSource());
    for (const tag of tags) {
      assert.doesNotMatch(tag.name, /^(image|script|a)$/i);
      for (const [key, value] of Object.entries(tag.attrs)) {
        if (key === "href" || key === "xlink:href") {
          assert.match(value, /^#/, `외부 참조: ${value}`);
        }
        if (key !== "xmlns") {
          assert.doesNotMatch(value, /https?:|\/\/|url\(\s*(?!#)/, `외부 참조: ${key}=${value}`);
        }
      }
    }
  });
});

describe("지운 자산", () => {
  for (const name of REMOVED_SVGS) {
    it(`public/${name} 가 없다`, () => {
      assert.equal(existsSync(join(PUBLIC, name)), false);
    });
  }

  it("src 어디서도 지운 파일을 참조하지 않는다", () => {
    const pattern = /(?<![\w-])(?:file|globe|next|vercel|window)\.svg\b|favicon\.ico/;
    const files = sourceFiles(SRC).filter((path) => path !== THIS_FILE);
    assert.ok(files.length > 100, `훑은 파일이 너무 적다: ${files.length}`);

    const offenders = files.filter((path) => pattern.test(read(path)));
    assert.deepEqual(offenders, []);
  });
});
