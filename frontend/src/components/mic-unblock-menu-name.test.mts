/**
 * 마이크를 다시 켜는 길(MIC_UNBLOCK_STEPS)에 적힌 앱 이름·메뉴 이름을 앱 설정과 대조한다.
 *
 * 실행: cd frontend && npm test
 *
 * 폰 설정 → 앱 정보의 "앱 설정 링크" 이름은 안드로이드 기본이 "앱 추가 설정",
 * 갤럭시(안드로이드 15 이상)가 "<앱 이름>에서 상세설정" 이다. 앱 정보 제목과 <앱 이름>
 * 자리에는 앱의 이름표(AndroidManifest 의 application android:label = @string/appName)가
 * 나온다. 그 값은 android/twa-manifest.json 의 name 이고, build.gradle 의 name 으로 옮겨져
 * 빌드된다. launcherName 은 홈 화면 아이콘 이름이라 여기서 보지 않는다.
 *
 * 네 자리(MicGate·MicCheck·TalkFeedback·TalkBoard)가 같은 상수를 그리는지는
 * mic-blocked-help-dynamic.test.mts 가 본다. 여기서는 상수의 내용만 본다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { MIC_UNBLOCK_STEPS } from "@/components/TalkFeedback";

const ANDROID = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "android");

/** twa-manifest.json 의 name. 앱 정보 화면에 나오는 이름이다. */
const APP_NAME: string = JSON.parse(readFileSync(join(ANDROID, "twa-manifest.json"), "utf8")).name;

/** build.gradle 의 name. 실제 빌드에 들어가는 값이다. */
const GRADLE_NAME = readFileSync(join(ANDROID, "app", "build.gradle"), "utf8").match(
  /^\s*name:\s*'([^']*)'/m,
)?.[1];

const BASE_MENU = "'앱 추가 설정'";
const galaxyMenu = (appName: string) => `'${appName}에서 상세설정'`;

/** 문구가 지켜야 할 것. 사보타주에서 틀린 문구에도 같은 검사를 돌린다. */
function checkSteps(steps: string, appName: string) {
  const at = (part: string) => {
    const i = steps.indexOf(part);
    assert.ok(i >= 0, `문구에 ${part} 가 없다`);
    return i;
  };
  const appInfo = at(`${appName} 앱 정보`);
  const menu = at(galaxyMenu(appName));
  at(BASE_MENU);
  const turnOn = at("마이크를 켜");
  assert.ok(appInfo < menu, "앱 정보를 연 다음에 메뉴를 누른다");
  assert.ok(menu < turnOn, "메뉴를 누른 다음에 마이크를 켠다");
  // 옛 문장(기본 메뉴 이름만 적은 것)이 남지 않았다
  assert.ok(!steps.includes(`${BASE_MENU}에서 마이크를`), "옛 문장이 남았다");
}

describe("마이크를 다시 켜는 메뉴 이름", () => {
  it("twa-manifest.json 과 build.gradle 의 앱 이름이 같다", () => {
    assert.ok(APP_NAME, "twa-manifest.json 에 name 이 없다");
    assert.equal(GRADLE_NAME, APP_NAME);
  });

  it("문구의 앱 이름·메뉴 이름·순서가 앱 이름과 맞는다", () => {
    checkSteps(MIC_UNBLOCK_STEPS, APP_NAME);
  });

  describe("사보타주: 검사가 실제로 무는지", () => {
    it("바뀌기 전 문구는 걸린다", () => {
      const old =
        "폰 설정에서 DeVoca 앱 정보를 열고 '앱 추가 설정'에서 마이크를 켜주세요. 그 설정 화면 맨 위에 'Android 설정' 안내가 보이면 눌러서 크롬의 마이크도 허용해주세요.";
      assert.throws(() => checkSteps(old, APP_NAME));
    });

    it("앱 이름이 바뀌면 지금 문구가 걸린다", () => {
      assert.throws(() => checkSteps(MIC_UNBLOCK_STEPS, `${APP_NAME}X`));
    });

    it("메뉴 이름과 마이크 켜기 순서가 뒤집히면 걸린다", () => {
      const swapped = `폰 설정에서 ${APP_NAME} 앱 정보를 열고 마이크를 켜주세요. ${galaxyMenu(APP_NAME)}(폰에 따라 ${BASE_MENU})`;
      assert.throws(() => checkSteps(swapped, APP_NAME));
    });
  });
});
