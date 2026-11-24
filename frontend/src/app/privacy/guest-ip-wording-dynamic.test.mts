/**
 * 처리방침 v6: 로그인하지 않은 문제풀기·순위표·소리내어 읽기를 IP 로 센다는 말이 제 절에 있는가.
 *
 * 실행: cd frontend && npm test
 *
 * 14절 항목과 날짜는 changes-section-dynamic·policy-wording-dynamic·policy-notice-v6 테스트가
 * 본다. 여기서는 14절 다섯째 항목이 가리키는 "2절 마목, 3절, 6절" 에 실제로 그 말이 있는지,
 * 그리고 v5 한 줄의 날짜를 본다. 14절이 가리키는 절을 지우거나 옮겨도 14절 테스트는 초록이다.
 *
 * 백엔드가 세는 것(apps/learning·vocab 의 throttles)과 말이 어긋나면 안 된다. 세는 자리
 * 셋(문제풀기, 순위표, 소리내어 읽기)을 이름으로 하나씩 찾는다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("next/link", {
  defaultExport: (props: { href: string; children: ReactNode }) =>
    createElement("a", { href: props.href }, props.children),
});

const { default: PrivacyPage } = await import("./page");
const { DOC_VERSION } = await import("../../components/LegalDoc");

const html = renderToStaticMarkup(createElement(PrivacyPage));

function section(id: string): string {
  const match = html.match(new RegExp(`<section[^>]*id="${id}"[^>]*>([\\s\\S]*?)</section>`));
  assert.ok(match, `${id} 절이 렌더돼야 한다`);
  // 줄바꿈이 낀 JSX 글자를 한 칸으로 모은다.
  return match[1].replace(/<[^>]+>/g, "").replace(/\s+/g, " ");
}

/** 세 자리를 모두 말하고, 로그인하지 않았을 때이고, IP 를 말하는 문장이 있다. */
function assertGuestIpSentence(text: string, where: string) {
  const sentences = text.split(/(?<=다\.|\))\s/);
  const hit = sentences.find(
    (s) =>
      s.includes("로그인하지 않고") &&
      s.includes("문제풀기") &&
      s.includes("순위표") &&
      s.includes("소리내어 읽기") &&
      s.includes("IP 주소"),
  );
  assert.ok(hit, `${where} 에 로그인하지 않은 요청의 IP 문장이 없다\n${text}`);
}

describe("처리방침 v6 - 로그인하지 않은 요청의 IP", { skip: DOC_VERSION !== "v6" }, () => {
  it("2절 마목(로그인하지 않은 이용자)에 있다", () => {
    const items = section("items");
    const ma = items.slice(items.indexOf("마. 로그인하지 않은 이용자"));
    assert.ok(ma.startsWith("마."), "2절 마목을 못 찾았다");
    assertGuestIpSentence(ma, "2절 마목");
    assert.match(ma, /해시값/);
  });

  it("3절(보유·이용 기간)의 요청 횟수 제한 기록에 있다", () => {
    const retention = section("retention");
    assertGuestIpSentence(retention, "3절");
    // 로그인한 뒤의 요청은 여전히 회원 번호로 센다. 그 말이 지워지면 로그인한 사람도 IP 로
    // 센다고 읽힌다.
    assert.match(retention, /로그인한 뒤의 요청은 회원 번호로 셉니다/);
  });

  it("6절(처리 위탁)의 넘어가는 정보에 있고 원문을 저장하지 않는다고 적는다", () => {
    const processors = section("processors");
    assertGuestIpSentence(processors, "6절");
    assert.match(processors, /원문은 저장하지 않습니다/);
  });

  it("14절 다섯째 항목이 2절 마목·3절·6절을 가리키고 11월 25일부터 한다", () => {
    const changes = section("changes");
    assert.match(
      changes,
      /로그인하지 않고 문제풀기·순위표·소리내어 읽기를 쓸 때도[^.]*\(2절 마목, 3절, 6절\)\. 이것도 시행일을 기다리지 않고 2026년 11월 25일부터 합니다/,
    );
  });

  it("v5 네 가지는 11월 21일 공고, 11월 28일 시행 한 줄로 남는다", () => {
    const changes = section("changes");
    assert.match(
      changes,
      /v5 로 2026년 11월 21일에 공고했고, 2026년 11월 28일에 시행합니다/,
    );
  });
});
