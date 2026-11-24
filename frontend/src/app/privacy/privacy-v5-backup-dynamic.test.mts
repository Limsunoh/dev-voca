/**
 * 처리방침 v5 에 더한 운영자 DB 백업(매일, 14일 보관) 문구를 화면 결과로 깨뜨려 보는 테스트.
 *
 * 실행: cd frontend && npx tsx --test --experimental-test-module-mocks src/app/privacy/privacy-v5-backup-dynamic.test.mts
 *
 * 계약:
 *   - 처리방침과 계정 삭제 안내에서 백업을 말하는 문장의 기간은 모두 14일이다.
 *     옛 문구("운영자가 따로 만드는 백업은 없습니다")는 어디에도 없다.
 *   - 14절의 백업 항목이 적은 절(3·4·6절)이 실제로 백업을 말하는 절과 같다.
 *   - 계정 삭제 안내 4절의 기간은 모두 처리방침 3·4절에 있는 기간이다.
 * 홈 알림 날짜와 문서 버전은 components/policy-notice-v6.test.mts 와 legal-pages.test.mts 가 본다.
 *
 * 검사는 함수로 두고, 각 함수가 실제로 무는지 일부러 틀린 입력을 넣어 확인한다
 * (구현 파일은 건드리지 않는다). v5 의 문구를 글자로 박은 테스트라 v5·v6 에서만 돈다.
 * v6 은 v5 시행(11-28) 전에 공고해서 14절에 v5 의 백업 항목이 그대로 있다. 그 다음
 * 개정에서 건너뛰면 이 파일을 지운다.
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

const { DOC_VERSION } = await import("../../components/LegalDoc");
const { default: PrivacyPage } = await import("./page");
const { default: TermsPage } = await import("../terms/page");
const { default: DeleteAccountPage } = await import("../delete-account/page");

const SKIP = !["v5", "v6"].includes(DOC_VERSION);

const privacyHtml = renderToStaticMarkup(createElement(PrivacyPage));
const termsHtml = renderToStaticMarkup(createElement(TermsPage));
const deleteHtml = renderToStaticMarkup(createElement(DeleteAccountPage));


/** 태그·주석을 지우고 공백을 하나로 모은 글. */
function text(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<\/li>/g, ". ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

function section(html: string, id: string): string {
  const body = html.match(
    new RegExp(`<section[^>]*id="${id}"[^>]*>([\\s\\S]*?)</section>`),
  )?.[1];
  assert.ok(body, `${id} 절이 없음`);
  return body;
}

function sectionIds(html: string): string[] {
  return [...html.matchAll(/<section[^>]*id="([^"]+)"/g)].map((m) => m[1]);
}

/** 절 제목 앞의 번호("3. 보유·이용 기간" 의 3). */
function sectionNumber(html: string, id: string): number {
  const title = text(section(html, id)).match(/^(\d+)\./)?.[1];
  assert.ok(title, `${id} 절 제목에 번호가 없음`);
  return Number(title);
}

function sentences(plain: string): string[] {
  return plain.split(/(?<=[.다])\s+/);
}

/** "14일", "1시간" 같은 기간. "11월 21일" 처럼 월 뒤의 날짜는 뺀다. */
function durations(plain: string): string[] {
  return [...plain.matchAll(/(?<!월\s?)(?<!\d)(\d+)\s?(일|시간)/g)].map(
    (m) => `${m[1]}${m[2]}`,
  );
}

// ---------------------------------------------------------------------------
// 검사 함수. 아래 "일부러 틀린 입력" 절이 이 함수들이 실제로 무는지 본다.
// ---------------------------------------------------------------------------

const OLD_PHRASES = [
  /따로 만드는 백업은 없/,
  /Railway 는\s*자체 정책에 따라 고객 데이터를 매일 백업하며/,
  /<li>Railway 의 데이터베이스 백업:/,
];

function checkNoOldPhrases(...htmls: string[]) {
  for (const html of htmls) {
    for (const old of OLD_PHRASES) assert.doesNotMatch(html, old);
  }
}

/** 백업을 말하는 문장마다 기간이 있으면 14일뿐이다. */
function checkBackupDays(html: string) {
  const checked = [];
  for (const sentence of sentences(text(html))) {
    if (!sentence.includes("백업")) continue;
    for (const d of durations(sentence)) {
      assert.equal(d, "14일", `백업 문장에 14일이 아닌 기간: ${sentence}`);
      checked.push(d);
    }
  }
  assert.ok(checked.length > 0, "14일을 적은 백업 문장이 하나도 없음");
}

function checkRetentionSays(privacy: string) {
  const retention = text(section(privacy, "retention"));
  assert.match(retention, /2026년 11월 21일부터 운영자가 매일 한 번/);
  assert.match(retention, /싱가포르/);
  assert.match(retention, /14일이 지난 백업은 자동으로 지웁니다/);
}

/** 14절의 v5 항목이 가리키는 절 = 백업을 말하는 절(14절 제외). */
function checkCitedSections(privacy: string) {
  const changes = text(section(privacy, "changes"));
  const v5Item = changes.match(/운영자가 데이터베이스를 매일 백업해[^)]*\(([^)]+)\)/)?.[1];
  assert.ok(v5Item, "14절에 백업 항목이 없음");
  const cited = new Set([...v5Item.matchAll(/(\d+)절/g)].map((m) => Number(m[1])));
  const mentioning = new Set(
    sectionIds(privacy)
      .filter((id) => id !== "changes" && text(section(privacy, id)).includes("백업"))
      .map((id) => sectionNumber(privacy, id)),
  );
  assert.deepEqual([...mentioning].sort(), [...cited].sort());
}

/** 삭제 안내 4절의 기간은 모두 처리방침 3·4절에 있다. */
function checkDeleteDurationsMatchPrivacy(privacy: string, del: string) {
  const policy = new Set(
    durations(text(section(privacy, "retention") + section(privacy, "destruction"))),
  );
  const kept = durations(text(section(del, "kept")));
  assert.ok(kept.includes("14일"), "삭제 안내 4절에 14일이 없음");
  for (const d of kept) assert.ok(policy.has(d), `삭제 안내의 ${d} 가 처리방침 3·4절에 없음`);
}

describe("v5 처리방침·계정 삭제 안내의 백업 문구", { skip: SKIP }, () => {
  it("옛 백업 문구가 처리방침·약관·계정 삭제 안내 어디에도 없다", () => {
    checkNoOldPhrases(privacyHtml, termsHtml, deleteHtml);
  });

  it("처리방침 3절이 시작일·매일·싱가포르·14일을 적는다", () => {
    checkRetentionSays(privacyHtml);
  });

  it("처리방침에서 백업을 말하는 문장의 기간은 모두 14일이다", () => {
    checkBackupDays(privacyHtml);
  });

  it("계정 삭제 안내에서 백업을 말하는 문장의 기간은 모두 14일이다", () => {
    checkBackupDays(deleteHtml);
  });

  it("14절 백업 항목이 적은 절이 실제로 백업을 말하는 절과 같다", () => {
    checkCitedSections(privacyHtml);
  });

  it("계정 삭제 안내 4절의 기간은 모두 처리방침 3·4절에 있다", () => {
    checkDeleteDurationsMatchPrivacy(privacyHtml, deleteHtml);
  });
});

describe("일부러 틀린 입력을 넣으면 검사가 문다", { skip: SKIP }, () => {
  it("3절을 옛 문구로 되돌리면 옛 문구 검사와 3절 검사가 실패한다", () => {
    const retention = section(privacyHtml, "retention");
    const oldRetention = retention.replace(
      /데이터베이스 백업: 2026년[\s\S]*?<\/li>/,
      "데이터베이스 백업: 운영자가 따로 만드는 백업은 없습니다. Railway 는 자체 정책에 따라 고객 데이터를 매일 백업하며, 그 보관 기간은 Railway 의 정책을 따릅니다.</li>",
    );
    assert.notEqual(oldRetention, retention, "바꿀 자리를 못 찾음");
    const broken = privacyHtml.replace(retention, oldRetention);
    assert.throws(() => checkNoOldPhrases(broken));
    assert.throws(() => checkRetentionSays(broken));
  });

  it("계정 삭제 안내의 백업 기간만 7일로 바꾸면 기간 검사가 실패한다", () => {
    const broken = deleteHtml.replace("삭제한 날부터 최대 14일", "삭제한 날부터 최대 7일");
    assert.notEqual(broken, deleteHtml);
    assert.throws(() => checkBackupDays(broken));
    assert.throws(() => checkDeleteDurationsMatchPrivacy(privacyHtml, broken));
  });

  it("처리방침 4절의 백업만 30일로 바꾸면 기간 검사가 실패한다", () => {
    const broken = privacyHtml.replace(
      "운영자가 만든 데이터베이스 백업은 14일이 지나면",
      "운영자가 만든 데이터베이스 백업은 30일이 지나면",
    );
    assert.notEqual(broken, privacyHtml);
    assert.throws(() => checkBackupDays(broken));
  });

  it("6절에서 백업 보관을 빼면 14절이 적은 절과 어긋난다", () => {
    const broken = privacyHtml.replace(", 데이터베이스 백업 보관", "");
    assert.notEqual(broken, privacyHtml);
    assert.throws(() => checkCitedSections(broken));
  });
});
