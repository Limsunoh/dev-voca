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
 *   - 처리방침 시행일은 공고일 7일 뒤다. 서버가 오류 메시지를 남기기 시작하는
 *     날(error_mail.py 의 MESSAGE_FROM)은 14절에 적은 v3 시행일과 같다.
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

const { DOC_VERSION, koreanDate, PRIVACY_CHANGE } = await import(
  "../../components/LegalDoc"
);

// v3 시행일. v4 를 v3 시행 전에 공고해 PRIVACY_CHANGE 는 v4 날짜이고, v3 날짜는
// 14절과 본문에 글자로 박혀 있다. 서버의 날짜 문(MESSAGE_FROM 등)은 이 날 켜진다.
const V3_EFFECTIVE = "2026-11-19";
// v3 의 날짜 문이 아직 코드에 있는 버전. 날짜 문을 지울 때 이것을 쓰는 절도 지운다.
const V3_GATES_LIVE = ["v3", "v4"].includes(DOC_VERSION);
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

  // 다음 버전에서 시행일을 고칠 때 MESSAGE_FROM 을 같이 미루면, 이미 켜진 메시지
  // 기록이 말없이 꺼진다. 그래서 PRIVACY_CHANGE 가 아니라 v3 시행일과 견준다.
  // 날짜 문을 지울 때(error_mail.py 의 ponytail 주석) 이 테스트도 지운다.
  it("v3: 서버가 오류 메시지를 남기기 시작하는 날이 14절의 v3 시행일과 같다", {
    skip: !V3_GATES_LIVE,
  }, () => {
    // 서버가 먼저 켜지면 처리방침이 알리기 전에 메시지를 남긴다.
    const source = readFileSync(
      new URL("../../../../backend/apps/accounts/error_mail.py", import.meta.url),
      "utf-8",
    );
    const m = source.match(/^MESSAGE_FROM = date\((\d+), (\d+), (\d+)\)/m);
    assert.ok(m, "MESSAGE_FROM 을 못 찾았다");
    const server = [m[1], m[2].padStart(2, "0"), m[3].padStart(2, "0")].join("-");
    assert.equal(server, V3_EFFECTIVE);
    assert.ok(pages.privacy.includes(`${koreanDate(V3_EFFECTIVE)} 시행`), "14절에 v3 시행일이 없다");
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

  // v3 에서 바뀐 내용이다. v3 시행 전에 v4 를 공고해 v4 의 14절에도 남는다.
  // 다음 개정에서 14절을 새로 쓰면 이 테스트는 건너뛴다.
  it("v3: 14절이 오류 메시지와 IP 주소 세기를 바뀐 내용으로 적는다", {
    skip: !V3_GATES_LIVE,
  }, () => {
    const changes = pages.privacy.match(
      /<section[^>]*id="changes"[^>]*>([\s\S]*?)<\/section>/,
    )?.[1];
    assert.ok(changes);
    assert.match(changes, /오류 메시지/);
    assert.match(changes, /IP 주소/);
  });

  it("14절이 구글 로그인 계정 창(11월 13일부터 적용)을 적는다", () => {
    // #192 가 v3 공지 기간에 더한 항목이다. v4 의 14절을 다시 쓰며 합칠 때 빠지기
    // 쉬웠다. 본문(2·6·7·10절)의 구글 문장은 그대로 있는데 14절만 빠지면 "v2 와
    // 같다" 고 잘못 알린다.
    const changes = pages.privacy.match(
      /<section[^>]*id="changes"[^>]*>([\s\S]*?)<\/section>/,
    )?.[1];
    assert.ok(changes);
    assert.match(changes, /구글 로그인 부분은 2026년 11월 13일부터\s+적용합니다/);
    assert.match(changes, /10절의 쿠키 목록과 마지막 문단/);
    assert.match(changes, /로그인\s+토큰, 4절 6번/);
  });

  it("v4: 14절이 로그인 토큰 30일을 바뀐 내용으로 적는다", {
    skip: DOC_VERSION !== "v4",
  }, () => {
    const changes = pages.privacy.match(
      /<section[^>]*id="changes"[^>]*>([\s\S]*?)<\/section>/,
    )?.[1];
    assert.ok(changes);
    assert.match(changes, /로그인 토큰을 발급하고 30일이 지나면 지웁니다/);
  });

  it("로그인 토큰은 발급 30일 뒤 지운다고 적는다", () => {
    // 백엔드 LoginToken.LIFETIME 과 로그인 쿠키(session.ts 의 MAX_AGE)가 30일이다
    // (tests_daily_cleanup.py 가 둘을 견준다). 옛 문구가 남으면 만료가 없다고 읽힌다.
    const retention = pages.privacy.match(
      /<section[^>]*id="retention"[^>]*>([\s\S]*?)<\/section>/,
    )?.[1];
    assert.ok(retention);
    assert.match(retention, /로그인 토큰: 발급 후 30일이 지나면/);
    assert.match(retention, /로그인 쿠키: 30일/);
    assert.doesNotMatch(pages.privacy, /정해진 만료 없이/);
  });

  it("IP 주소는 원문이 아니라 해시값으로만 둔다고 적는다", () => {
    // 가입·로그인 시도를 IP 주소로도 센다(백엔드 요청 제한). 원문을 저장한다고
    // 읽히면 안 되고, "IP 를 저장하지 않는다" 는 옛 단정이 남아도 안 된다.
    // 날짜는 IP 로 세기 시작한 날이라 글자로 박혀 있어야 한다(PRIVACY_CHANGE 와 무관).
    const retention = pages.privacy.match(
      /<section[^>]*id="retention"[^>]*>([\s\S]*?)<\/section>/,
    )?.[1];
    assert.ok(retention);
    assert.match(retention, /2026년\s+11월 19일부터는 이메일 로그인·가입 시도를 접속한 IP 주소로도 셉니다/);
    assert.match(retention, /원문을 저장하지 않고/);
    assert.doesNotMatch(pages.privacy, /IP 주소나 브라우저 정보를 저장하지 않습니다/);
    assert.doesNotMatch(pages.privacy + pages["delete-account"], /알아볼 수 없게 바꾼/);
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
