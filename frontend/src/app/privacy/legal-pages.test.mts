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

const { DOC_VERSION } = await import("../../components/LegalDoc");
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
    assert.match(html, /devvoca 계정 삭제 안내/);
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
