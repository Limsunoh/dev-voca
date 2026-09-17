/**
 * 학습 카드에서 보던 자리를 잃지 않는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함 둘이다. 카드를 여덟 장 넘기다 새로고침하면 **첫 장으로
 * 돌아갔고**, 잘못 넘긴 카드를 다시 볼 방법이 판이 끝날 때까지 없었다.
 * 넘긴 자리는 서버에 안 알리므로(StudyCards 머리말) 화면이 기억하지 않으면
 * 아무도 모른다.
 *
 * 브라우저를 띄우는 테스트 판이 저장소에 없어서 원문으로 본다
 * (reaction-overlay.test.mts 가 같은 이유로 같은 방식이다).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const code = readFileSync(join(HERE, "StudyCards.tsx"), "utf8").replace(/\r\n/g, "\n");

describe("학습 카드는 보던 자리를 지킨다", () => {
  it("카드 번호를 탭에 적어 새로고침해도 이어진다", () => {
    assert.match(code, /sessionStorage/, "어딘가에 적지 않으면 새로고침에 첫 장으로 간다");
    // 묶음마다 따로 적어야 한다. 한 값으로 쓰면 다음 묶음이 중간부터 시작한다.
    assert.match(code, /daily-card-\$\{chunkIndex\}/);
    // **그냥 읽으면 안 된다.** 첫 화면은 서버가 그려 보내는데 서버에는
    // 브라우저 저장소가 없다. 그리면서 읽으면 서버가 보낸 화면과 달라져
    // ("이전" 버튼 하나가 통째로 어긋난다) 리액트가 그 자리를 다시 그린다.
    assert.doesNotMatch(code, /useState\(\(\) => read\(/);
    // 리액트 바깥 값을 읽는 전용 훅을 쓴다. 서버 몫으로 0 을 따로 준다.
    assert.match(code, /useSyncExternalStore\(/);
    assert.match(code, /\(\) => read\(memoryKey\),\s*\(\) => 0,/);
  });

  it("카드를 넘길 때마다 적는다", () => {
    // 상태를 직접 바꾸면 그 자리만 안 적혀 조용히 어긋난다.
    const direct = code.match(/setPicked\(/g) ?? [];
    assert.equal(direct.length, 1, "setPicked 은 goTo 안에서만 부른다");
    assert.match(code, /const goTo = \(next: number\) => \{[\s\S]*?save\(/);
  });

  it("저장이 막힌 브라우저에서도 화면이 뜬다", () => {
    // 사생활 보호 창에서는 접근 자체가 예외를 던진다. 못 막으면 학습
    // 화면이 통째로 안 뜬다 - 편의 하나 때문에 기능을 잃는다.
    const reads = code.slice(code.indexOf("function read"), code.indexOf("export function"));
    assert.match(reads, /try \{[\s\S]*?catch/);
    assert.equal((reads.match(/catch/g) ?? []).length, 2, "읽기와 쓰기 양쪽을 막아야 한다");
  });

  it("적어둔 번호가 카드 수보다 커도 화면이 어긋나지 않는다", () => {
    // 묶음 크기는 판마다 달라질 수 있는데 적어두는 키는 묶음 번호뿐이라,
    // 탭을 열어둔 채 새 판을 시작하면 지난 판의 번호를 읽는다. 카드만
    // 자르고 표시를 안 자르면 "6/3" 이 뜨고 "이전" 이 한 번 헛돈다.
    assert.match(code, /const at = Math\.min\(rawAt, cards\.length - 1\);/);
    // 자른 값 하나로 카드·마지막 판정·표시가 다 간다.
    assert.match(code, /const card = cards\[at\];/);
    assert.match(code, /const last = at >= cards\.length - 1;/);
    assert.match(code, /\{at \+ 1\}\/\{cards\.length\}/);
    // 자르기 전 값을 그대로 쓰는 자리가 남으면 안 된다.
    assert.equal((code.match(/rawAt/g) ?? []).length, 2, "rawAt 은 선언과 자르기에서만");
  });

  it("되돌아갈 버튼이 있다", () => {
    assert.match(code, /이전/);
    assert.match(code, /goTo\(at - 1\)/);
    // 첫 장에서는 안 그린다. 눌러도 갈 곳이 없다.
    assert.match(code, /\{at > 0 && \(/);
  });
});
