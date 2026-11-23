/**
 * 처리방침·약관·계정 삭제 안내에 쓰면 안 되는 것이 남지 않았는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 초안의 표시([확인 필요] 등)와 부록이 화면에 나가지 않는다.
 *   - 운영자가 공개하기로 한 연락처는 이메일뿐이다. 휴대전화 번호가 없다.
 *   - 목차의 링크는 모두 실제 절을 가리킨다.
 *   - 문서 버전은 가입할 때 저장하는 TERMS_VERSION 과 같다.
 *   - 처리방침 시행일은 공고일 7일 뒤다.
 *   - 로그인 토큰은 발급 30일 뒤 지운다고 적고, "정해진 만료 없이" 가 남지 않는다.
 *   - 홈의 처리방침 알림은 시행일 전날까지만 뜨고 14절로 간다.
 *   - IP 주소는 원문이 아니라 서버 비밀값을 섞은 해시값으로만 둔다고 적고,
 *     "IP 주소를 저장하지 않는다" 는 옛 단정이 남지 않는다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it, mock } from "node:test";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// 여기서 볼 것은 주소뿐이다. next/link 는 브라우저 라우터를 기대한다.
mock.module("next/link", {
  defaultExport: (props: { href: string; children: ReactNode }) =>
    createElement("a", { href: props.href }, props.children),
});

const { DOC_VERSION, PRIVACY_CHANGE } = await import(
  "../../components/LegalDoc"
);
const { PolicyNotice } = await import("../../components/PolicyNotice");
const { default: TermsPage } = await import("../terms/page");
const { default: PrivacyPage } = await import("./page");
const { default: DeleteAccountPage } = await import("../delete-account/page");

const pages = {
  privacy: renderToStaticMarkup(createElement(PrivacyPage)),
  terms: renderToStaticMarkup(createElement(TermsPage)),
  "delete-account": renderToStaticMarkup(createElement(DeleteAccountPage)),
};

describe("처리방침·약관·계정 삭제 안내 화면", () => {
  for (const [name, html] of Object.entries(pages)) {
    it(`${name}: 초안의 표시와 부록이 남지 않는다`, () => {
      assert.doesNotMatch(html, /\[(확인 필요|주의|법률 검토)|부록|게시 전|초안 v/);
    });

    it(`${name}: 휴대전화 번호가 없다`, () => {
      assert.doesNotMatch(html, /01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}/);
    });

    it(`${name}: 목차의 링크가 모두 실제 절을 가리킨다`, () => {
      const targets = [...html.matchAll(/href="#([^"]+)"/g)].map((m) => m[1]);
      assert.ok(targets.length > 0);
      for (const id of targets) {
        assert.ok(html.includes(`id="${id}"`), `없는 절: ${id}`);
      }
    });

    it(`${name}: 글꼴 라이선스를 알린다`, () => {
      assert.match(html, /SIL Open Font License 1\.1/);
    });
  }

  it("처리방침이 업체마다 받는 자의 연락처를 적는다", () => {
    for (const contact of [
      "privacy@vercel.com",
      "privacy@railway.com",
      "googlekrsupport@google.com",
    ]) {
      assert.ok(pages.privacy.includes(contact), contact);
    }
  });

  it("계정 삭제 안내가 앱 이름과 요청 연락처를 적는다", () => {
    // Google Play 가 요구하는 웹 주소의 조건이다. 동의를 받는 문서가 아니라
    // 버전 줄은 없다.
    const html = pages["delete-account"];
    assert.match(html, /DeVoca 계정 삭제 안내/);
    assert.match(html, /mailto:/);
    assert.doesNotMatch(html, /버전 v/);
    assert.match(pages.privacy, /href="\/delete-account"/);
  });

  it("문서 버전이 가입할 때 저장하는 버전과 같다", () => {
    const models = readFileSync(
      new URL("../../../../backend/apps/accounts/models.py", import.meta.url),
      "utf-8",
    );
    const saved = models.match(/^TERMS_VERSION = "([^"]+)"/m)?.[1];
    assert.equal(DOC_VERSION, saved);
  });
});

describe("처리방침 변경 공고", () => {
  const { announced, effective } = PRIVACY_CHANGE;

  /** "2026-11-12" 에 days 를 더한 날. 시각대가 끼지 않게 UTC 로 센다. */
  function addDays(iso: string, days: number): string {
    const d = new Date(`${iso}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
  }

  it("시행일이 공고일에서 7일 이상 뒤다(14절의 약속)", () => {
    // 문자열 비교로 충분하다. 둘 다 YYYY-MM-DD 다.
    assert.ok(effective >= addDays(announced, 7), `${announced} -> ${effective}`);
  });

  it("14절이 공고일과 시행일을 적는다", () => {
    const changes = pages.privacy.match(
      /<section[^>]*id="changes"[^>]*>([\s\S]*?)<\/section>/,
    )?.[1];
    assert.ok(changes);
    const korean = (iso: string) => {
      const [y, m, d] = iso.split("-").map(Number);
      return `${y}년 ${m}월 ${d}일`;
    };
    assert.match(changes, new RegExp(`공고일: ${korean(announced)}`));
    assert.match(changes, new RegExp(`시행일: ${korean(effective)}`));
  });

  it("v5: Sentry 를 사목·3·6·7절과 14절에 적는다", {
    skip: DOC_VERSION !== "v5",
  }, () => {
    const section = (id: string) =>
      pages.privacy.match(new RegExp(`<section[^>]*id="${id}"[^>]*>([\\s\\S]*?)</section>`))?.[1] ?? "";
    for (const id of ["items", "retention", "processors", "transfer", "changes"]) {
      assert.match(section(id), /Sentry/, id);
    }
    assert.match(section("transfer"), /compliance@sentry\.io/);
    assert.match(section("items"), /IP\s+주소를 저장하지 않도록 설정했습니다/);
    assert.match(section("items"), /앱 화면에서는 오류가 났을 때만\s+보냅니다/);
    // v5 에서 새로 센 관리자 화면 로그인 시도는 3절과 14절 바뀐 내용에 남는다.
    assert.match(section("retention"), /관리자 화면 로그인 시도는 이메일로/);
    assert.match(section("changes"), /관리자 화면\s+로그인 시도도 이메일 해시값으로 셉니다/);
    assert.match(pages["delete-account"], /Sentry 로 보낸 오류 기록/);
  });

  it("로그인 토큰은 발급 30일 뒤 지우고, 쓰는 동안은 이어 간다고 적는다", () => {
    // 백엔드 LoginToken.LIFETIME 과 로그인 쿠키(token-cookie.ts 의 TOKEN_MAX_AGE)가 30일이다
    // (tests_daily_cleanup.py 가 둘을 견준다). 옛 문구가 남으면 만료가 없다고 읽힌다.
    // 하루마다 새 토큰으로 바꾸므로(LoginToken.renew) "로그인하고 30일" 로 읽히면 안 된다.
    const retention = pages.privacy.match(
      /<section[^>]*id="retention"[^>]*>([\s\S]*?)<\/section>/,
    )?.[1];
    assert.ok(retention);
    assert.match(retention, /로그인 토큰: 발급 후 30일이 지나면/);
    assert.match(retention, /30일 동안\s+이용하지 않으면 로그인이 끝납니다/);
    assert.match(retention, /로그인 쿠키: 로그인하거나 새 토큰을 받은 때부터 30일/);
    assert.doesNotMatch(pages.privacy, /정해진 만료 없이/);
  });

  it("운영자 DB 백업을 시작한 날과 14일 보관을 적고, 옛 단정이 남지 않는다", () => {
    // 3절이 실제 백업 설정(DEPLOY.md 의 "DB 백업" 절: 매일, 14일)과 맞아야 한다.
    // 옛 문구 "운영자가 따로 만드는 백업은 없습니다" 가 남으면 백업이 없다고 읽힌다.
    const retention = pages.privacy.match(
      /<section[^>]*id="retention"[^>]*>([\s\S]*?)<\/section>/,
    )?.[1];
    assert.ok(retention);
    assert.match(retention, /2026년 11월 21일부터 운영자가 매일 한 번 데이터베이스\s+전체를 백업/);
    assert.match(retention, /14일이 지난 백업은\s+자동으로 지웁니다/);
    assert.doesNotMatch(pages.privacy, /따로 만드는 백업은 없습니다/);
  });

  it("IP 주소는 원문이 아니라 해시값으로만 둔다고 적는다", () => {
    // 가입·로그인 시도를 IP 주소로도 센다(백엔드 요청 제한). 원문을 저장한다고
    // 읽히면 안 되고, "IP 를 저장하지 않는다" 는 옛 단정이 남아도 안 된다.
    const section = (id: string) =>
      pages.privacy.match(new RegExp(`<section[^>]*id="${id}"[^>]*>([\\s\\S]*?)</section>`))?.[1] ?? "";
    assert.match(section("items"), /IP 주소를\s+서버 비밀값을 섞은 해시값으로 바꿔/);
    assert.match(section("retention"), /둘 다 서버 비밀값을 섞은\s+해시값으로 바꿔 둡니다/);
    assert.match(section("processors"), /해시값으로 바꾸는 데만 쓰고 원문은\s+저장하지 않습니다/);
    assert.doesNotMatch(pages.privacy, /IP 주소나 브라우저 정보를 저장하지 않습니다/);
    // IPv4 는 43억 개뿐이라 비밀값을 가진 사람은 전부 해시해 원문을 찾을 수 있다(08879bc).
    // 해시를 "되돌릴 수 없게 바꾼 값" 같은 센 말로 풀지 않는다(계정 삭제를 되돌릴 수
    // 없다는 3절 문장은 다른 이야기라 막지 않는다).
    assert.doesNotMatch(pages.privacy + pages["delete-account"], /알아볼 수 없게 바꾼|되돌릴 수 없게 바꾼/);
  });

  it("홈 알림은 시행일 전날까지 뜨고 14절로 간다", () => {
    const render = (today: string) =>
      renderToStaticMarkup(createElement(PolicyNotice, { today }));
    for (const today of [announced, addDays(effective, -1)]) {
      const html = render(today);
      assert.match(html, /href="\/privacy#changes"/, today);
      assert.match(html, /처리방침/, today);
    }
    assert.equal(render(effective), "");
    assert.equal(render(addDays(effective, 30)), "");
  });
});
