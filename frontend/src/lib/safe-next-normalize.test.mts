/**
 * safeNext 가 돌려주는 값이 어떤 입력에서도 안쪽 주소인지, 그리고 한 번 더 태워도
 * 같은지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * safe-next-dot-segments.test.mts 가 대표적인 점 조각 몇 개를 본다. 여기서는
 *   - 인코딩된 점(%2e, %2E%2E, .%2e)과 역슬래시·탭·줄바꿈이 섞인 꼴
 *   - 한 번 더 인코딩된 값(%252e)이 두 번 풀려 점이 되지 않는지
 *   - 한글 경로·쿼리·해시가 풀었을 때 원래 글자로 돌아오는지
 *   - 조각 몇 개를 모든 순서로 이어 붙인 입력 전부에 대해 성립해야 하는 것
 * 을 민다.
 *
 * 마지막 것은 난수가 아니라 정해진 조각을 길이 4 까지 빠짐없이 이어 붙인다.
 * 돌릴 때마다 같은 입력이라 실패하면 늘 같은 줄에서 실패한다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { safeNext } from "./routes";

const SITE = "https://dev-voca.vercel.app";

/**
 * 돌려준 값을 실제 화면 주소 기준으로 풀었을 때 우리 사이트 안인가.
 *
 * 한 번 풀고 끝내면 "/.//evil.example" 도 통과한다 - 풀린 경로가 "//evil.example"
 * 이어도 출처는 아직 우리 사이트다. 화면 쪽 Next 가 그 풀린 경로를 다시 주소로
 * 읽을 때 바깥으로 나가므로, 풀린 경로를 한 번 더 푼 것까지 본다.
 */
function staysHome(out: string): boolean {
  const once = new URL(out, `${SITE}/test/review/deep`);
  const again = new URL(once.pathname + once.search + once.hash, SITE);
  return once.origin === SITE && again.origin === SITE;
}

describe("인코딩된 점·역슬래시·탭으로 만든 바깥 주소는 홈으로", () => {
  for (const value of [
    "/%2E%2E//evil.example",
    "/%2e%2e/%2e%2e//evil.example",
    "/.%2e//evil.example",
    "/%2e./evil.example/..//evil.example",
    "/.\\/evil.example/..//x",
    "/.\\\\evil.example",
    "/.\t//evil.example",
    "/\t.//evil.example",
    "/.\r\n//evil.example",
    "/a/b/../../..//evil.example",
    "/..///evil.example",
    "/%2e/%2e%2e/\\/evil.example",
  ]) {
    it(JSON.stringify(value), () => {
      assert.equal(safeNext(value), "/");
    });
  }
});

describe("두 번 인코딩된 점은 한 번만 풀리고 안쪽에 머문다", () => {
  for (const value of ["/%252e//evil.example", "/%25252e%25252e//evil.example", "/.%09//evil.example"]) {
    it(value, () => {
      const out = safeNext(value);
      assert.equal(out, value, "한 번 더 풀었다");
      assert.ok(staysHome(out));
      assert.equal(safeNext(out), out);
    });
  }

  it("인코딩된 슬래시·역슬래시는 경로 구분자로 풀지 않는다", () => {
    for (const value of ["/%2f%2fevil.example", "/%5c%5cevil.example", "/..%2f..%2f/evil.example"]) {
      assert.equal(safeNext(value), value);
    }
  });
});

describe("쿼리·해시와 한글", () => {
  it("쿼리·해시 안의 // 는 그대로 둔다(경로가 아니다)", () => {
    assert.equal(safeNext("/x?y=//evil.example"), "/x?y=//evil.example");
    assert.equal(safeNext("/x#//evil.example"), "/x#//evil.example");
  });

  it("한글 쿼리는 인코딩해 돌려주고, 풀면 원래 검색어다", () => {
    const out = safeNext("/learn/words?search=한글&page=2");
    const url = new URL(out, SITE);
    assert.equal(url.pathname, "/learn/words");
    assert.equal(url.searchParams.get("search"), "한글");
    assert.equal(url.searchParams.get("page"), "2");
    assert.equal(safeNext(out), out, "한 번 더 태우면 또 인코딩됐다");
  });

  it("한글 경로·해시도 같다", () => {
    const out = safeNext("/learn/한글#제목");
    const url = new URL(out, SITE);
    assert.equal(decodeURIComponent(url.pathname), "/learn/한글");
    assert.equal(decodeURIComponent(url.hash), "#제목");
    assert.equal(safeNext(out), out);
  });

  it("빈 쿼리·빈 해시는 떨어진다", () => {
    assert.equal(safeNext("/x?"), "/x");
    assert.equal(safeNext("/x#"), "/x");
  });
});

describe("문자열이 아닌 값은 홈으로", () => {
  for (const value of [null, undefined, 42, ["/board"], { toString: () => "/board" }, new File([], "x")]) {
    it(String(value), () => {
      assert.equal(safeNext(value), "/");
    });
  }
});

describe("조각을 이어 붙인 모든 입력에서", () => {
  const parts = ["/", "\\", ".", "..", "%2e", "%2E", "%2f", "%5c", "\t", "%25", "?", "#", "evil"];
  const inputs: string[] = [];
  const grow = (prefix: string, depth: number) => {
    inputs.push(prefix);
    if (depth === 0) return;
    for (const p of parts) grow(prefix + p, depth - 1);
  };
  grow("/", 4);

  it(`${inputs.length}개 모두 안쪽이고 // 로 시작하지 않으며, 한 번 더 태워도 같다`, () => {
    for (const value of inputs) {
      let out: string;
      try {
        out = safeNext(value);
      } catch (error) {
        assert.fail(`${JSON.stringify(value)} 에서 던졌다: ${String(error)}`);
      }
      const where = `${JSON.stringify(value)} -> ${JSON.stringify(out)}`;
      assert.ok(out.startsWith("/"), where);
      assert.ok(!out.startsWith("//"), where);
      assert.ok(!out.startsWith("/\\"), where);
      assert.ok(staysHome(out), where);
      assert.equal(safeNext(out), out, where);
    }
  });
});
