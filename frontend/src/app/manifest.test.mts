/**
 * 앱 설치 정보(manifest)와 끊김 안내 검증.
 *
 * 실행: cd frontend && npm test
 *
 * Android 앱(TWA) 껍데기를 만드는 Bubblewrap 이 manifest 의 아이콘 주소를 그대로
 * 받아 간다. 파일이 없거나 적힌 크기와 실제 크기가 다르면 껍데기를 만들 때에야
 * 깨지거나, 런처 아이콘이 흐리게 나온다.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PUBLIC = join(HERE, "../../public");
// 다른 화면 테스트처럼 동적 import 로 default 를 꺼낸다. 정적 import 는 tsx 가
// CommonJS 로 감싸 default 가 함수가 아니게 된다.
const { default: manifest } = await import("./manifest");
const data = manifest();

/** PNG 머리(IHDR)의 가로·세로·색 형식과 투명 표(tRNS)가 있는지. */
function pngInfo(file: string) {
  const buf = readFileSync(file);
  assert.equal(buf.toString("latin1", 12, 16), "IHDR", `${file} 이 PNG 가 아니다`);
  // 덩어리(chunk)를 차례로 읽어 이름만 모은다. 파일 전체에서 "tRNS" 를 찾으면
  // 압축된 그림 데이터에 우연히 같은 네 글자가 나와 틀리게 걸릴 수 있다.
  const chunks: string[] = [];
  for (let at = 8; at < buf.length; at += 12 + buf.readUInt32BE(at)) {
    chunks.push(buf.toString("latin1", at + 4, at + 8));
  }
  return {
    size: `${buf.readUInt32BE(16)}x${buf.readUInt32BE(20)}`,
    colorType: buf[25],
    hasTransparency: chunks.includes("tRNS"),
  };
}

describe("앱 설치 정보", () => {
  it("앱처럼 열리고 첫 화면이 사이트 처음이다", () => {
    assert.equal(data.display, "standalone");
    assert.equal(data.start_url, "/");
    assert.equal(data.scope, "/");
  });

  it("바탕·상태 표시줄 색이 layout 의 themeColor 와 같다", () => {
    const layout = readFileSync(join(HERE, "layout.tsx"), "utf8");
    const theme = layout.match(/themeColor:\s*"([^"]+)"/)?.[1];
    assert.ok(theme, "layout.tsx 에서 themeColor 를 못 찾았다");
    assert.equal(data.theme_color, theme);
    assert.equal(data.background_color, theme);
  });

  it("아이콘 파일이 있고 적힌 크기와 실제 크기가 같다", () => {
    assert.ok(data.icons?.length);
    for (const icon of data.icons ?? []) {
      const file = join(PUBLIC, icon.src);
      assert.ok(existsSync(file), `${icon.src} 가 없다`);
      assert.equal(pngInfo(file).size, icon.sizes, icon.src);
    }
  });

  it("192 와 512 아이콘, 잘려도 되는 maskable 아이콘이 있다", () => {
    const sizes = (purpose: string) =>
      (data.icons ?? []).filter((i) => i.purpose === purpose).map((i) => i.sizes);
    assert.deepEqual(sizes("any").sort(), ["192x192", "512x512"]);
    assert.deepEqual(sizes("maskable"), ["512x512"]);
  });

  it("maskable 아이콘은 투명한 곳이 없다", () => {
    // 런처가 원으로 자를 때 투명한 모서리가 있으면 그 자리가 검게 나온다.
    const icon = (data.icons ?? []).find((i) => i.purpose === "maskable")!;
    const info = pngInfo(join(PUBLIC, icon.src));
    assert.ok([2, 3].includes(info.colorType), `알파가 있는 형식이다(색 형식 ${info.colorType})`);
    assert.equal(info.hasTransparency, false, "투명 표(tRNS)가 있다");
  });
});

describe("Android 앱(TWA)과 웹을 잇는 확인 파일", () => {
  const twa = JSON.parse(readFileSync(join(HERE, "../../../android/twa-manifest.json"), "utf8"));
  const links = JSON.parse(readFileSync(join(PUBLIC, ".well-known/assetlinks.json"), "utf8"));

  it("assetlinks.json 의 패키지 이름이 Android 앱과 같다", () => {
    // 다르면 앱 위에 주소창이 뜬다. 패키지 이름은 스토어에 올린 뒤 못 바꾼다.
    assert.equal(links[0].target.package_name, twa.packageId);
    assert.equal(twa.packageId, "com.devvoca.app");
  });

  it("서명 지문이 SHA-256 형식이다", () => {
    const prints: string[] = links[0].target.sha256_cert_fingerprints;
    assert.ok(prints.length >= 1);
    for (const p of prints) assert.match(p, /^([0-9A-F]{2}:){31}[0-9A-F]{2}$/);
  });

  // 지금은 업로드 키 지문 하나다. Play 에서 받은 앱은 Play 앱 서명 키로 서명되어,
  // 그 지문이 없으면 앱 위에 주소창이 뜬다. 더하면 이 줄을 지운다.
  it.todo("Play 앱 서명 키 지문을 assetlinks.json 에 더한다 (android/README.md)");

  it("Android 앱이 이 웹의 이름·시작 주소를 쓴다", () => {
    assert.equal(twa.host, "dev-voca.vercel.app");
    assert.equal(twa.startUrl, data.start_url);
    assert.equal(twa.name, data.name);
    // 폰 아이콘 밑에 뜨는 이름. 웹의 짧은 이름과 같은 자리다.
    assert.equal(twa.launcherName, data.short_name);
    assert.equal(twa.backgroundColor.toLowerCase(), data.background_color);
    assert.equal(twa.themeColor.toLowerCase(), data.theme_color);
    // 웹은 밝은 화면만 있다. 폰이 다크 모드여도 앱 테두리가 검게 바뀌지 않아야 한다.
    assert.equal(twa.themeColorDark, twa.themeColor);
    assert.equal(twa.navigationColorDark, twa.navigationColor);
    assert.equal(twa.navigationDividerColorDark, twa.navigationDividerColor);
  });
});

describe("끊김 안내 service worker", () => {
  const sw = readFileSync(join(PUBLIC, "sw.js"), "utf8");

  it("미리 받아 두는 안내 화면이 실제로 있다", () => {
    const url = sw.match(/OFFLINE_URL = "([^"]+)"/)?.[1];
    assert.ok(url, "sw.js 에서 OFFLINE_URL 을 못 찾았다");
    assert.ok(existsSync(join(PUBLIC, url)), `${url} 가 없다`);
  });

  it("화면 이동 요청만 가로챈다", () => {
    // API·그림까지 가로채 캐시에서 내주면 배포한 내용이 앱에 바로 안 나간다.
    assert.match(sw, /request\.mode !== "navigate"\) return;/);
  });

  it("안내 화면의 바탕과 상태 표시줄 색이 globals.css 의 --background 와 같다", () => {
    const css = readFileSync(join(HERE, "globals.css"), "utf8");
    const background = css.match(/--background:\s*(#[0-9a-f]{6})\s*;/i)?.[1]?.toLowerCase();
    const html = readFileSync(join(PUBLIC, "offline.html"), "utf8").toLowerCase();
    assert.ok(background);
    assert.match(html, new RegExp(`name="theme-color" content="${background}"`));
    assert.match(html, new RegExp(`background:\\s*${background}`));
  });

  it("안내 화면은 밖에서 아무것도 받지 않는다", () => {
    // 인터넷이 없을 때 뜨는 화면이라 외부 글꼴·CSS·스크립트를 부르면 깨진다.
    const html = readFileSync(join(PUBLIC, "offline.html"), "utf8");
    assert.doesNotMatch(html, /<(link|script)[^>]+(href|src)=/i);
  });
});
