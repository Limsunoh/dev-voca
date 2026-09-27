/**
 * 긴 덩어리에 줄바꿈 자리(<wbr>)를 넣는 도우미.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 것: URL·경로가 폰에서 낱말 가운데("de|mo.git")에서 끊기던 것.
 * 자리는 20자 넘는 덩어리의 `/` 뒤·`.` 앞·소문자 다음 대문자 앞에만 넣는다. 짧은 덩어리·숫자·
 * 앞 점·문장 끝 마침표는 건드리지 않는다(그러면 줄 끝에서 쪼개진다).
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { withWrapPoints } from "./wrap-points";

const html = (text: string) =>
  renderToStaticMarkup(createElement("p", null, withWrapPoints(text)));

describe("withWrapPoints", () => {
  it("URL 은 / 뒤와 . 앞에서 끊을 수 있다", () => {
    assert.equal(
      html("error: failed to push some refs to 'https://github.com/acme/demo.git'"),
      "<p>error: failed to push some refs to &#x27;https://<wbr/>github<wbr/>.com/<wbr/>acme/<wbr/>demo<wbr/>.git&#x27;</p>",
    );
  });

  it("점으로 이은 긴 이름은 . 앞과 낱말 경계(소문자 다음 대문자)에서 끊는다", () => {
    assert.equal(
      html("java.lang.UnsupportedClassVersionError: Hello"),
      "<p>java<wbr/>.lang<wbr/>.Unsupported<wbr/>Class<wbr/>Version<wbr/>Error: Hello</p>",
    );
  });

  it("20자 이하 덩어리는 건드리지 않는다", () => {
    assert.equal(withWrapPoints("at config/settings.py:1"), "at config/settings.py:1");
    assert.equal(
      html("at config/settings.py:14"),
      "<p>at config/<wbr/>settings<wbr/>.py:14</p>",
    );
    for (const text of [
      "CONFLICT (content): Merge conflict in src/app.py",
      "Tag this commit as v2.0.0 and push the tag.",
      "Bind for 0.0.0.0:8080 failed: ____ is already allocated",
      "fatal: not a git repository (or any of the parent directories): .git",
    ]) {
      assert.equal(withWrapPoints(text), text, text);
    }
  });

  it("긴 덩어리 안이라도 숫자 사이·앞 점·끝 마침표·닫는 따옴표 앞에는 넣지 않는다", () => {
    assert.equal(
      html("'https://example.com/'"),
      "<p>&#x27;https://<wbr/>example<wbr/>.com/&#x27;</p>",
    );
    // 점 앞 글자가 영숫자가 아니면(말줄임) 넣지 않는다.
    assert.equal(
      withWrapPoints("see foo...bar_baz_qux_quux_corge"),
      "see foo...bar_baz_qux_quux_corge",
    );
    assert.equal(
      html("see https://registry.npmjs.org/react-18.2.0.tgz."),
      "<p>see https://<wbr/>registry<wbr/>.npmjs<wbr/>.org/<wbr/>react-18.2.0<wbr/>.tgz.</p>",
    );
    assert.equal(
      html("/home/someone/.config/app.json"),
      "<p>/home/<wbr/>someone/<wbr/>.config/<wbr/>app<wbr/>.json</p>",
    );
  });

  it("넣을 자리가 없으면 글을 그대로 돌려준다", () => {
    assert.equal(withWrapPoints("fatal: refusing to merge"), "fatal: refusing to merge");
    assert.equal(withWrapPoints(""), "");
  });
});
