/**
 * WrongAnswer 를 **실제로 그려서** 본다.
 *
 * 형제 파일 wrong-answer.test.mts 는 호출부(세 화면)가 값을 넘기는지를
 * 원문으로 본다. 여기는 이 조각이 **무엇을 그리는지**를 본다. 원문 검사는
 * "값을 그리긴 하는데 엉뚱한 자리" 를 못 잡는다. react-dom/server 로
 * 글자를 뽑아 보므로 브라우저가 필요 없다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { WrongAnswer } from "./WrongAnswer";

const draw = (text: string, extra: string, label?: string) =>
  renderToStaticMarkup(
    WrongAnswer(label === undefined ? { text, extra } : { label, text, extra }) as never,
  );

describe("WrongAnswer 가 그리는 것", () => {
  it("본문과 뜻을 둘 다 그린다", () => {
    const html = draw("rebase", "브랜치를 옮겨 붙이기");
    assert.match(html, /오답/);
    assert.match(html, /rebase/);
    assert.match(html, /브랜치를 옮겨 붙이기/);
  });

  it("뜻은 본문 뒤에 온다", () => {
    // 순서가 뒤집히면 "오답 · 뜻 / 단어" 가 되어 무엇이 정답인지 흐려진다.
    const html = draw("rebase", "뜻뜻");
    assert.ok(html.indexOf("rebase") < html.indexOf("뜻뜻"));
  });

  it("뜻이 없으면 빈 줄을 안 만든다", () => {
    const html = draw("rebase", "");
    assert.match(html, /rebase/);
    assert.doesNotMatch(html, /<span/, "빈 뜻에 span 을 만들면 줄만 벌어진다");
  });

  it("둘 다 비면 말머리만 남고 가운뎃점이 안 붙는다", () => {
    const html = draw("", "");
    assert.equal(html.replace(/<!--[^>]*-->/g, "").trim(), "오답");
    assert.doesNotMatch(html, /·/);
  });

  it("본문만 비고 뜻이 있으면 뜻을 지킨다", () => {
    // 서버가 실제로 내는 조합이다 - Sentence.context 를 비우면
    // _describe 가 ("", 해석) 을 준다. 백엔드 테스트로 확인했다.
    const html = draw("", "이 브랜치를 리베이스해 주세요");
    assert.match(html, /이 브랜치를 리베이스해 주세요/, "서버가 보낸 뜻이 사라지면 안 된다");
    // 본문이 없으니 가운뎃점도 없어야 한다.
    assert.doesNotMatch(html, /·/, "본문이 없는데 가운뎃점이 뜨면 뒤가 잘린 것처럼 보인다");
  });

  it("넘긴 문제는 말머리가 '넘김' 이다", () => {
    const html = draw("rebase", "뜻", "넘김");
    assert.match(html, /넘김 · rebase/);
    assert.doesNotMatch(html, /오답/, "넘긴 것을 오답이라 하면 벌처럼 읽힌다");
  });

  it("말머리가 비어도 정답은 남는다", () => {
    const html = draw("rebase", "뜻", "");
    assert.match(html, /rebase/);
    assert.match(html, /뜻/);
  });

  it("꺾쇠가 든 값을 이스케이프한다", () => {
    const html = draw("<script>x</script>", "<b>뜻</b>");
    assert.doesNotMatch(html, /<script>/);
    assert.doesNotMatch(html, /<b>/);
  });

  it("아주 긴 값도 통째로 그린다", () => {
    const long = "가".repeat(5000);
    const html = draw(long, long);
    assert.ok(html.includes(long));
  });

  it("줄바꿈이 든 값은 그대로 들어간다", () => {
    // markup 에는 남지만 HTML 은 white-space 기본값에서 한 줄로 뭉갠다.
    const html = draw("첫\n둘", "해석\n두 줄");
    assert.match(html, /첫\n둘/);
  });

  it("공백만 든 본문은 없는 것으로 본다", () => {
    // 빈 값만 막으면 공백 한 칸이 통과해 "오답 · " 로 끝난다. Admin 폼은
    // 공백을 깎지만 시드나 AI 파이프라인처럼 폼을 안 타는 쓰기는 그대로
    // 들어온다.
    assert.equal(draw("   ", ""), "오답");
    assert.equal(draw("   ", "  뜻  "), "오답<span style=\"display:block;color:var(--text-muted);font-weight:var(--weight-bold)\">뜻</span>");
  });
});
