/**
 * 처리방침 14절(처리방침 변경)을 실제로 렌더해서 본다.
 *
 * 실행: cd frontend && npx tsx --test --experimental-test-module-mocks src/app/privacy/changes-section-dynamic.test.mts
 *
 * 계약:
 *   - 14절 목록은 다섯 항목이다. 공고일, 시행일, 이번 버전의 바뀐 내용 셋(v5 일 때만 본다).
 *   - 앞 버전 이력("이전 버전" 줄, v2·v3·v4 와 그 시행일)은 페이지 어디에도 없다.
 *   - 공고일·시행일 칸은 PRIVACY_CHANGE 에서 온다. 시행일은 공고일보다 7일 이상 뒤다
 *     (14절 첫 문장이 "시행 7일 전부터 알립니다" 를 약속한다).
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// next/link 는 브라우저 라우터를 기대한다. 여기서 볼 것은 글자뿐이다.
mock.module("next/link", {
  defaultExport: (props: { href: string; children: ReactNode }) =>
    createElement("a", { href: props.href }, props.children),
});

const { default: PrivacyPage } = await import("./page");
const { DOC_VERSION, PRIVACY_CHANGE, koreanDate } = await import("../../components/LegalDoc");

const html = renderToStaticMarkup(createElement(PrivacyPage));

function changesSection(): string {
  const match = html.match(/<section[^>]*id="changes"[^>]*>([\s\S]*?)<\/section>/);
  assert.ok(match, "14절 section 이 렌더돼야 한다");
  return match[1];
}

function items(section: string): string[] {
  return [...section.matchAll(/<li[^>]*>([\s\S]*?)<\/li>/g)].map((m) =>
    m[1].replace(/<[^>]+>/g, ""),
  );
}

describe("처리방침 14절", () => {
  // 바뀐 내용이 셋인 것은 v5 의 사정이다. 다음 개정 때 항목 수를 새 버전에 맞춘다.
  it("목록은 다섯 항목이고 공고일·시행일이 맨 앞 둘이다", { skip: DOC_VERSION !== "v5" }, () => {
    const list = items(changesSection());

    assert.equal(list.length, 5, list.join("\n"));
    assert.equal(list[0], `공고일: ${koreanDate(PRIVACY_CHANGE.announced)}`);
    assert.equal(list[1], `시행일: ${koreanDate(PRIVACY_CHANGE.effective)}`);
    for (const item of list.slice(2)) {
      assert.doesNotMatch(item, /^(공고일|시행일|이전 버전)/);
    }
  });

  it("앞 버전 이력이 14절에 없다", () => {
    const text = changesSection().replace(/<[^>]+>/g, "");

    assert.doesNotMatch(text, /이전 버전/);
    assert.doesNotMatch(text, /\bv[1-4]\b/);
    for (const old of ["2026년 11월 9일", "2026년 11월 19일", "2026년 11월 20일 시행"]) {
      assert.ok(!text.includes(old), `14절에 옛 시행일 "${old}" 가 남았다`);
    }
  });

  it("페이지 어디에도 '이전 버전' 줄이 없다", () => {
    assert.doesNotMatch(html.replace(/<[^>]+>/g, ""), /이전 버전/);
  });

  it("시행일은 공고일보다 7일 이상 뒤다", () => {
    const day = 24 * 60 * 60 * 1000;
    const gap =
      (Date.parse(PRIVACY_CHANGE.effective) - Date.parse(PRIVACY_CHANGE.announced)) / day;

    assert.ok(gap >= 7, `공고 ${PRIVACY_CHANGE.announced} -> 시행 ${PRIVACY_CHANGE.effective}`);
  });

  it("목차에서 14절로 가는 링크가 남아 있다", () => {
    assert.match(html, /href="#changes"[^>]*>[\s\S]*?14\. 처리방침 변경/);
  });
});
