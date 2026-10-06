/**
 * withWrapPoints 의 `::` · `_` 규칙을 손으로 적은 기대값으로 확인한다.
 *
 * 실행: cd frontend && npm test
 *
 * edge 테스트의 expected() 는 구현과 같은 규칙으로 쓰여 있어 구현이 틀리면 같이 틀린다.
 * 여기서는 기대 문자열을 직접 적었다. "|" 가 <wbr> 한 개를 뜻한다(입력에는 "|" 를 쓰지 않는다).
 *
 * 규칙: 21자 이상 덩어리 안에서
 * - `::` 바로 뒤, 다음 글자가 영숫자일 때
 * - 영숫자 바로 다음의 `_` 하나 뒤, 다음 글자가 영숫자일 때
 * 콜론 하나("localhost:8080")와 이어진 밑줄("__init__", "____")에는 넣지 않는다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isValidElement, type ReactNode } from "react";

import { withWrapPoints } from "./wrap-points";

/** 돌려받은 값을 <wbr> 는 "|" 로, 나머지 글은 그대로 이어 붙인다. */
function marked(text: string): string {
  assert.ok(!text.includes("|"), "입력에 | 를 쓰지 말 것");
  const out: ReactNode = withWrapPoints(text);
  if (typeof out === "string") return out;
  assert.ok(Array.isArray(out), "문자열 아니면 배열이어야 한다");
  return out
    .map((part) => {
      if (typeof part === "string") return part;
      assert.ok(isValidElement(part) && part.type === "wbr", "wbr 외 요소가 섞였다");
      return "|";
    })
    .join("");
}

/** 입력 -> 기대값 목록을 한꺼번에 확인한다. 걷어낸 결과는 항상 원문이어야 한다. */
function check(cases: Array<[string, string]>) {
  for (const [input, want] of cases) {
    const got = marked(input);
    assert.equal(got, want, `입력 ${JSON.stringify(input)}`);
    assert.equal(got.replace(/\|/g, ""), input);
  }
}

describe("withWrapPoints - :: 와 _ 규칙(손으로 적은 기대값)", () => {
  it("실제 에러 문장", () => {
    check([
      ["net::ERR_CONNECTION_REFUSED", "net::|ERR_|CONNECTION_|REFUSED"],
      ["[SSL: CERTIFICATE_VERIFY_FAILED]", "[SSL: CERTIFICATE_|VERIFY_|FAILED]"],
      ["Error [ERR_HTTP_HEADERS_SENT]: x", "Error [ERR_|HTTP_|HEADERS_|SENT]: x"],
      ["std::vector<std::string>::iterator", "std::|vector<std::|string>::|iterator"],
      ["snake_case_long_identifier_name", "snake_|case_|long_|identifier_|name"],
      ["my_package_name/__init__.py", "my_|package_|name/|__init__.py"],
      ["https://example.com/very_long_path_here", "https://|example|.com/|very_|long_|path_|here"],
    ]);
  });

  it("21자 경계: 21자는 넣고 20자는 안 넣는다", () => {
    check([
      ["ERR_HTTP_HEADERS_SENT", "ERR_|HTTP_|HEADERS_|SENT"], // 21
      ["ERR_HTTP_HEADERS_SEN", "ERR_HTTP_HEADERS_SEN"], // 20
      ["abcdefghijklmnopqrst_u", "abcdefghijklmnopqrst_|u"], // 22
    ]);
  });

  it("짧은 덩어리는 그대로", () => {
    check([
      ["net::ERR_*", "net::ERR_*"],
      ["std::vector<int>", "std::vector<int>"],
      ["__init__.py", "__init__.py"],
      ["SCREAMING_CASE", "SCREAMING_CASE"],
      ["a_b_c", "a_b_c"],
      ["[SSL: x]", "[SSL: x]"],
    ]);
  });

  it("짧은 덩어리는 긴 덩어리 옆에 있어도 그대로", () => {
    check([
      ["ab_cd x_y_zzzzzzzzzzzzzzzzzzzz_end", "ab_cd x_|y_|zzzzzzzzzzzzzzzzzzzz_|end"],
      ["a_b_c net::ERR_CONNECTION_REFUSED", "a_b_c net::|ERR_|CONNECTION_|REFUSED"],
    ]);
  });

  it("한 글자씩 이은 이름: 셋째 글자부터 본다", () => {
    check([["a_b_c_d_e_f_g_h_i_j_k_l", "a_|b_|c_|d_|e_|f_|g_|h_|i_|j_|k_|l"]]);
    check([["a_bcdefghijklmnopqrstuvw", "a_|bcdefghijklmnopqrstuvw"]]);
  });

  it("빈칸 표시와 붙은 밑줄에는 넣지 않는다", () => {
    check([
      ["____________________", "____________________"], // 20
      ["_____________________", "_____________________"], // 21
      ["ERR_____________________", "ERR_____________________"],
      ["____________________ABC", "____________________ABC"],
      ["__init__abcdefghijklmnopq", "__init__abcdefghijklmnopq"],
      ["abcdefghijklmnopqrstuvwxyz_", "abcdefghijklmnopqrstuvwxyz_"], // 뒤에 글자가 없다
      ["abcdefghijklmnopqrst__uvwxyz", "abcdefghijklmnopqrst__uvwxyz"],
      ["abcdefghijklmnopqrst___uvwxyz", "abcdefghijklmnopqrst___uvwxyz"],
    ]);
  });

  it("밑줄 뒤 영숫자는 넣고, 이어진 밑줄 뒤는 안 넣는다(섞인 경우)", () => {
    check([
      ["ERR_____ABC_DEFGHIJKLMNOP", "ERR_____ABC_|DEFGHIJKLMNOP"],
      ["__init_subclass__call_xx", "__init_|subclass__call_|xx"],
      ["net::_private_member_name_x", "net::_private_|member_|name_|x"],
    ]);
  });

  it("콜론: 하나는 안 넣고 :: 만 넣는다", () => {
    check([
      ["localhost:8080:abcdefghijklmnop", "localhost:8080:abcdefghijklmnop"],
      ["error:abcdefghijklmnopqrstuvwxyz", "error:abcdefghijklmnopqrstuvwxyz"],
      ["http://localhost:8080/api/v1/users", "http://|localhost:8080/|api/|v1/|users"],
      [":::::::::::::::::::::::", ":::::::::::::::::::::::"],
      ["abcdefghijklmnopqrst::", "abcdefghijklmnopqrst::"], // 뒤에 글자가 없다
      ["abcdefghijklmnopqrst::-x", "abcdefghijklmnopqrst::-x"], // 뒤가 영숫자가 아니다
      ["abcdefghijklmnopqrst::_x", "abcdefghijklmnopqrst::_x"],
    ]);
  });

  it("덩어리 맨 앞의 ::", () => {
    check([
      ["::abcdefghijklmnopqrstu", "::|abcdefghijklmnopqrstu"],
      [":::abcdefghijklmnopqrst", ":::|abcdefghijklmnopqrst"],
    ]);
  });

  it("윈도 경로의 역슬래시와 콜론은 건드리지 않고 밑줄만 본다", () => {
    check([
      ["C:\\Users\\someone\\Documents\\x", "C:\\Users\\someone\\Documents\\x"],
      ["C:\\Users\\some_user\\My_Documents\\x", "C:\\Users\\some_|user\\My_|Documents\\x"],
    ]);
  });

  it("한글·이모지 옆", () => {
    check([
      ["한글_테스트_식별자_이름_네번째_다섯번째", "한글_테스트_식별자_이름_네번째_다섯번째"],
      ["한글ERR_CONNECTION_REFUSED한글", "한글ERR_|CONNECTION_|REFUSED한글"],
      ["🔥ERR_CONNECTION_REFUSED🔥", "🔥ERR_|CONNECTION_|REFUSED🔥"],
      ["ERR_🔥CONNECTION_REFUSED_x", "ERR_🔥CONNECTION_|REFUSED_|x"],
      ["net::🔥ERR_CONNECTION_REFUSED", "net::🔥ERR_|CONNECTION_|REFUSED"],
      ["net::한글ERR_CONNECTION_REFUSED", "net::한글ERR_|CONNECTION_|REFUSED"],
    ]);
  });

  it("무작위 입력에서도 걷어내면 원문이고 wbr 가 맨 끝·연속으로 나오지 않는다", () => {
    const alphabet = ["a", "Z", "1", "_", ":", "/", ".", "-", " ", "한", "🔥"];
    let seed = 12345;
    const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    for (let n = 0; n < 3000; n++) {
      const len = Math.floor(rnd() * 60);
      let s = "";
      for (let k = 0; k < len; k++) s += alphabet[Math.floor(rnd() * alphabet.length)];
      const got = marked(s);
      assert.equal(got.replace(/\|/g, ""), s, JSON.stringify(s));
      assert.ok(!got.endsWith("|") && !got.startsWith("|") && !got.includes("||"), got);
      // 20자 이하 덩어리에는 wbr 가 없다.
      for (const chunk of got.split(/\s+/)) {
        if (chunk.replace(/\|/g, "").length <= 20) assert.ok(!chunk.includes("|"), got);
      }
    }
  });
});
