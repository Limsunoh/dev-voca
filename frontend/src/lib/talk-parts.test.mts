/**
 * 낱말 짝짓기 검증.
 *
 * 실행: cd frontend && npx tsx --test src/lib/talk-parts.test.mts
 *
 * 여기 있는 값은 **지어낸 것이 아니라 실제 DB 에서 뽑은 것**이다. 강조가
 * 어긋나는 자리는 데이터의 성질에서 나오는데(하이픈·음절 단위 IPA·강세가
 * 공백을 걸치는 것), 가짜 값으로 시험하면 "그런 경우가 있겠나" 로 넘어가고
 * 정작 실물에서 깨진다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { alignParts, splitWords, stripSlashes, stripStress } from "./talk-parts";

describe("splitWords", () => {
  it("하이픈도 구분자로 쓴다", () => {
    // 공백만 쪼개면 client-side 가 한 덩이가 되어 발음기호 3개와 어긋난다.
    assert.deepEqual(splitWords("client-side routing"), [
      "client",
      "side",
      "routing",
    ]);
    assert.deepEqual(splitWords("end-to-end test"), [
      "end",
      "to",
      "end",
      "test",
    ]);
  });

  it("빈 조각을 남기지 않는다", () => {
    assert.deepEqual(splitWords("  pull   request  "), ["pull", "request"]);
  });
});

describe("stripSlashes", () => {
  it("바깥 슬래시만 뗀다", () => {
    assert.equal(stripSlashes("/ˈitæɡ/"), "ˈitæɡ");
    assert.equal(stripSlashes("/ˈpʊl rɪˌkwest/"), "ˈpʊl rɪˌkwest");
  });

  it("슬래시가 없어도 그대로 둔다", () => {
    // 일상 표현이 슬래시 없이 올 수도 있어서, 있을 때만 떼는 것을 확인한다.
    assert.equal(stripSlashes("wɛr ɪz ðə"), "wɛr ɪz ðə");
  });
});

describe("stripStress", () => {
  it("강세 별표를 걷어낸다", () => {
    assert.equal(stripStress("**쏘r s** 맾"), "쏘r s 맾");
  });
});

describe("alignParts", () => {
  it("여러 낱말을 낱말마다 짝짓는다", () => {
    const parts = alignParts(
      "pull request",
      "/ˈpʊl rɪˌkwest/",
      "**풀** 리퀘스트",
    );

    assert.ok(parts);
    assert.equal(parts.length, 2);
    assert.deepEqual(parts[0], {
      word: "pull",
      ipa: "ˈpʊl",
      reading: "**풀**",
    });
    // 그릴 때는 별표가 든 원본을 넘겨야 Reading 이 굵게 그린다.
    assert.equal(parts[1].reading, "리퀘스트");
  });

  it("하이픈이 든 것도 짝지어진다", () => {
    // 이것이 하이픈을 구분자로 넣은 이유다. 공백만 쪼개면 2 대 3 으로
    // 어긋나 강조가 통째로 사라진다.
    const parts = alignParts(
      "client-side routing",
      "/ˈklaɪənt saɪd ˌrutɪŋ/",
      "클라이언트 사이드 라우팅",
    );

    assert.ok(parts);
    assert.equal(parts.length, 3);
    assert.equal(parts[1].ipa, "saɪd");
  });

  it("낱말이 하나면 짝짓지 않는다", () => {
    // 강조할 자리가 없다. npm 처럼 IPA 가 음절로 쪼개진 것도 여기서 걸린다.
    assert.equal(alignParts("npm", "/ˌen pi ˈem/", "엔피엠"), null);
    assert.equal(alignParts("cache", "/kæʃ/", "캐시"), null);
  });

  it("강세가 공백을 걸치면 짝짓지 않는다", () => {
    // source map 이 실제로 이렇다. 별표를 걷으면 3조각이라 term(2)과
    // 어긋나므로, 엉뚱한 자리를 강조하느니 통째로 그린다.
    assert.equal(
      alignParts("source map", "/ˈsɔrs ˌmæp/", "**쏘r s** 맾"),
      null,
    );
  });

  it("발음기호 개수가 다르면 짝짓지 않는다", () => {
    assert.equal(
      alignParts("where is the restroom", "/wɛr ɪz ðə/", "웨어r 이z 더 레스트룸"),
      null,
    );
  });

  it("발음이 비어 있으면 짝짓지 않는다", () => {
    // pronunciation 과 reading 은 비워둘 수 있는 칸이다(갈리는 발음을
    // 억지로 채우지 않는다는 모델 주석). 그때 터지면 안 된다.
    assert.equal(alignParts("pull request", "", "풀 리퀘스트"), null);
    assert.equal(alignParts("pull request", "/ˈpʊl rɪˌkwest/", ""), null);
  });
});
