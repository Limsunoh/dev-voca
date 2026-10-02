/**
 * 오답 노트(/mistakes)가 줄마다 어떤 글꼴과 줄바꿈 자리로 그리는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 단어와 에러 메시지 문장은 고정폭, 실무 표현은 본문체다. 판정은 문제
 * 화면과 같은 isErrorSentence 로 한다(lib/quiz-text). 문장 글만 줄바꿈 자리
 * (<wbr>)를 받아 긴 URL 이 낱말 가운데서 잘리지 않는다.
 *
 * 카드 글에 break-words 를 붙이지 않는다. 그 클래스가 body 의
 * overflow-wrap: anywhere 를 덮어쓰면 고정폭 긴 이름이 grid 칸을 밀어
 * 좁은 폰에서 가로 스크롤이 생긴다(실제 폭은 브라우저에서만 보이므로 여기서는
 * 클래스가 없는지만 본다).
 *
 * 백엔드는 부르지 않는다. 목록 함수와 세션 모듈("server-only")을 대역으로
 * 바꾸고, 페이지가 돌려준 트리를 HTML 로 펴서 본다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";

mock.module("next/navigation", {
  namedExports: {
    redirect: (to: string) => {
      throw new Error(`redirect ${to}`);
    },
  },
});

mock.module("@/lib/session", {
  namedExports: { getToken: async () => "token" },
});

const ERROR_TEXT =
  "fatal: repository 'https://github.com/acme/demo.git/' not found";
const PHRASE_TEXT = "Could you take a look at https://github.com/acme/demo/pull/42?";

const rows = [
  {
    id: 1,
    target_type: "word",
    target_id: 11,
    text: "idempotency_key_for_payment_retries",
    meaning: "멱등 키",
    sentence_kind: "",
  },
  {
    id: 2,
    target_type: "sentence",
    target_id: 22,
    text: ERROR_TEXT,
    meaning: "저장소를 찾을 수 없음",
    sentence_kind: "error",
  },
  {
    id: 3,
    target_type: "sentence",
    target_id: 33,
    text: PHRASE_TEXT,
    meaning: "이것 좀 봐 줄래요?",
    sentence_kind: "phrase",
  },
];

mock.module("@/lib/api/history", {
  namedExports: {
    getMistakes: async () => ({
      count: rows.length,
      next: null,
      previous: null,
      results: rows,
    }),
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const MistakesPage = (await import("./page")).default;

const html = renderToStaticMarkup(
  await MistakesPage({ searchParams: Promise.resolve({}) }),
);

/** 상세 주소로 가는 카드 안의 첫 <p>(본문 글). [여는 태그, 안쪽]. */
function bodyOf(href: string): { open: string; inner: string } {
  const card = html.split(`href="${href}"`)[1];
  assert.ok(card, `${href} 카드가 없다`);
  const m = card.match(/(<p[^>]*>)([\s\S]*?)<\/p>/);
  assert.ok(m, `${href} 카드에 <p> 가 없다`);
  return { open: m[1], inner: m[2] };
}

const decode = (s: string) => s.replace(/&#x27;/g, "'").replace(/&amp;/g, "&");

describe("오답 노트 카드 글꼴", () => {
  it("단어는 고정폭이고 줄바꿈 자리를 받지 않는다", () => {
    const { open, inner } = bodyOf("/learn/words/11");
    assert.match(open, /class="font-mono"/);
    assert.doesNotMatch(inner, /<wbr/);
  });

  it("에러 메시지 문장은 고정폭이다", () => {
    assert.match(bodyOf("/learn/sentences/22").open, /class="font-mono"/);
  });

  it("실무 표현 문장은 본문체다", () => {
    assert.doesNotMatch(bodyOf("/learn/sentences/33").open, /class=/);
  });

  it("문장 글은 긴 URL 에 줄바꿈 자리를 받고, 빼면 원문과 같다", () => {
    for (const [href, text] of [
      ["/learn/sentences/22", ERROR_TEXT],
      ["/learn/sentences/33", PHRASE_TEXT],
    ]) {
      const { inner } = bodyOf(href);
      assert.match(inner, /<wbr\/>/, href);
      assert.equal(decode(inner.replace(/<wbr\/>/g, "")), text);
    }
  });

  it("카드 글 어디에도 break-words 가 없다", () => {
    assert.doesNotMatch(html, /break-words/);
  });
});
