/**
 * Android 앱(TWA)과 웹을 잇는 확인 파일이 앱 빌드 설정과 어긋나지 않는지 검증.
 *
 * 실행: cd frontend && npm test
 *
 * manifest.test.mts 는 assetlinks.json 을 twa-manifest.json 과만 맞춘다. 그런데
 * 실제로 폰에 깔리는 앱의 패키지 이름·주소는 Bubblewrap 이 옮겨 적은
 * android/app/build.gradle 에서 나온다. 셋 중 하나만 바뀌어도 Chrome 이 앱을
 * 이 웹의 주인으로 못 알아보고 앱 위에 주소창을 띄운다. 빌드해서 폰에 깔아
 * 보기 전에는 드러나지 않으므로 여기서 미리 맞춘다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ANDROID = join(HERE, "../../../android");
const LINKS_FILE = join(HERE, "../../public/.well-known/assetlinks.json");

const linksRaw = readFileSync(LINKS_FILE);
const links = JSON.parse(linksRaw.toString("utf8"));
const twa = JSON.parse(readFileSync(join(ANDROID, "twa-manifest.json"), "utf8"));
const gradle = readFileSync(join(ANDROID, "app/build.gradle"), "utf8");

/** build.gradle 에서 정규식 첫 그룹을 모두 꺼낸다. 하나도 없으면 실패. */
function gradleValues(re: RegExp, what: string): string[] {
  const found = [...gradle.matchAll(re)].map((m) => m[1]);
  assert.ok(found.length, `build.gradle 에서 ${what} 를 못 찾았다`);
  return found;
}

describe("assetlinks.json 형식", () => {
  it("BOM 없이 배열로 시작한다", () => {
    // Google 의 검사기는 JSON 앞에 BOM 이 붙으면 파일을 못 읽는다.
    assert.equal(linksRaw[0], "[".charCodeAt(0));
    assert.ok(Array.isArray(links) && links.length >= 1);
  });

  it("모든 항목이 android_app 대상이고 relation 이 handle_all_urls 다", () => {
    for (const s of links) {
      assert.deepEqual(s.relation, ["delegate_permission/common.handle_all_urls"]);
      assert.equal(s.target.namespace, "android_app");
    }
  });

  it("지문은 대문자 16진 두 자리씩 콜론으로 이은 32바이트이고 겹치지 않는다", () => {
    for (const s of links) {
      const prints: string[] = s.target.sha256_cert_fingerprints;
      assert.ok(prints.length >= 1);
      for (const p of prints) {
        assert.match(p, /^[0-9A-F]{2}(:[0-9A-F]{2}){31}$/, `지문 형식이 틀리다: ${p}`);
      }
      assert.equal(new Set(prints).size, prints.length, "같은 지문이 두 번 있다");
    }
  });
});

describe("assetlinks.json 과 Android 빌드 설정", () => {
  it("패키지 이름이 build.gradle 의 applicationId·namespace 와 같다", () => {
    const ids = [
      ...gradleValues(/applicationId:\s*'([^']+)'/g, "twaManifest.applicationId"),
      ...gradleValues(/^\s*applicationId\s+"([^"]+)"/gm, "defaultConfig.applicationId"),
      ...gradleValues(/^\s*namespace\s+"([^"]+)"/gm, "namespace"),
    ];
    for (const s of links) {
      for (const id of ids) assert.equal(s.target.package_name, id);
    }
    assert.equal(twa.packageId, ids[0]);
  });

  it("앱이 여는 도메인과 시작 주소가 twa-manifest 와 build.gradle 에서 같다", () => {
    const [host] = gradleValues(/hostName:\s*'([^']+)'/g, "hostName");
    const [launchUrl] = gradleValues(/launchUrl:\s*'([^']+)'/g, "launchUrl");
    assert.equal(twa.host, host);
    assert.equal(twa.startUrl, launchUrl);
    // 아이콘·manifest 주소가 다른 도메인이면 Bubblewrap 이 엉뚱한 사이트를 읽는다.
    for (const key of ["fullScopeUrl", "iconUrl", "maskableIconUrl", "webManifestUrl"]) {
      assert.equal(new URL(twa[key]).host, host, key);
    }
  });

  it("버전 번호가 twa-manifest 와 build.gradle 에서 같다", () => {
    // bubblewrap update 가 둘을 함께 올린다. 한쪽만 고치면 Play 가 이전 번호로 받는다.
    const [code] = gradleValues(/^\s*versionCode\s+(\d+)/gm, "versionCode");
    const [name] = gradleValues(/^\s*versionName\s+"([^"]+)"/gm, "versionName");
    assert.equal(twa.appVersionCode, Number(code));
    assert.equal(twa.appVersionName, name);
  });
});

describe("서명 키와 빌드 결과물이 저장소에 안 들어간다", () => {
  it("android/.gitignore 가 키·apk·aab·로그를 막는다", () => {
    const ignore = readFileSync(join(ANDROID, ".gitignore"), "utf8").split(/\r?\n/);
    for (const pattern of ["*.jks", "*.keystore", "*.apk", "*.aab", "*.log"]) {
      assert.ok(ignore.includes(pattern), `${pattern} 가 빠졌다`);
    }
  });
});
