/**
 * 채점 연출이 조건 가지 안에 들어가지 않았는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * ## 왜 이런 모양의 테스트인가
 *
 * 잡으려는 결함은 "**답도 안 했는데 지난 판정이 다시 재생된다**" 이다.
 * 보드들은 상태에 따라 서로 다른 트리를 돌려주는데(가져오는 중 · 학습 카드 ·
 * 결과 화면 · 본문), 연출을 그중 한 가지 안에 두면 가지가 바뀔 때 React 가
 * 언마운트했다가 돌아올 때 다시 마운트한다. fire 는 상태에 남아 있으므로
 * key 가 새로 붙어 처음부터 다시 뛴다.
 *
 * 실제로 세 번 났고 세 번 다 사용자가 찾았다.
 *
 *     문제풀기   "다음 문제" 를 누르면 loading 가지를 거친다
 *     일일학습   "이어서 익히기" 로 학습 카드에 갔다 온다
 *     판 모드    같은 구조였다
 *
 * 한 가지를 고치면 다음 가지에서 또 났다 - 가지는 계속 늘어나고 하나만
 * 빠뜨려도 같은 일이 난다. 그래서 개별 경로를 재지 않고 **구조 자체**를
 * 못 박는다: 연출은 overlays 안에서 딱 한 번 만들어지고, 그 overlays 는
 * 가지들보다 먼저 정의되어 출구 하나에서 그려진다.
 *
 * 화면을 띄워 재는 편이 낫지만 이 저장소에는 DOM 테스트 환경이 없다(node
 * 내장 러너로 순수 로직만 돌린다). 의존성을 늘리는 것보다 이 검사가 싸고,
 * 잡으려는 것이 정확히 "어디에 두었는가" 라서 원문 검사로 잡힌다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

const BOARDS = [
  "QuizBoard.tsx",
  "RoundBoard.tsx",
  "DailyStudyBoard.tsx",
  "ReviewBoard.tsx",
] as const;

function read(...parts: string[]): string {
  // 줄바꿈을 LF 로 맞춘다. 윈도우 체크아웃은 CRLF 라 "\n}\n" 같은 경계가
  // 안 잡히고, 그러면 컴포넌트 본체 대신 파일 끝까지 떼어 보게 된다 - 아래
  // 도우미 컴포넌트의 if 가 섞여 멀쩡한 코드가 빨개진다.
  return readFileSync(join(HERE, ...parts), "utf8").replace(/\r\n/g, "\n");
}

/** 주석을 걷어낸 원문. 주석 안의 `<Reaction` 이 검사에 걸리지 않게 한다. */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

function count(source: string, pattern: RegExp): number {
  return (source.match(pattern) ?? []).length;
}

describe("채점 연출은 조건 가지 밖에 있어야 한다", () => {
  for (const name of BOARDS) {
    const code = stripComments(read(name));
    /** 파일 위쪽 도우미 함수들은 빼고 컴포넌트 본체만 본다. */
    const fn = code.slice(code.indexOf("\nexport function "));

    it(`${name} 은 Reaction 과 Burst 를 한 번씩만 그린다`, () => {
      // 두 번 그리면 어느 하나가 가지 안에 있다는 뜻이다.
      assert.equal(count(code, /<Reaction\b/g), 1);
      assert.equal(count(code, /<Burst\b/g), 1);
    });

    it(`${name} 은 가지들보다 먼저 overlays 를 만든다`, () => {
      const overlaysAt = fn.indexOf("const overlays = (");
      assert.ok(overlaysAt > -1, "overlays 변수가 없다");

      // 가지는 두 모양 중 하나로 나타난다. 둘 다 overlays 보다 뒤여야 한다.
      for (const marker of ["const body = (() => {", "\n  if ("]) {
        const at = fn.indexOf(marker);
        if (at > -1) {
          assert.ok(
            overlaysAt < at,
            `overlays 가 가지(${marker.trim()}) 보다 뒤에 있다`,
          );
        }
      }
    });

    it(`${name} 은 가지 밖에서 overlays 를 그린다`, () => {
      // **여기가 핵심이다.** 만드는 자리만 보면 껍데기 검사가 된다 -
      // overlays 를 위에서 만들어 놓고 {overlays} 를 가지 안에서 그리면
      // 결함은 그대로인데 위 검사는 통과한다. 처음에 그렇게 썼다가
      // 버그를 되돌려 보고 안 잡히는 것을 확인하고 고쳤다.
      assert.equal(count(fn, /\{overlays\}/g), 1, "한 자리에서만 그려야 한다");

      const bodyEnd = fn.indexOf("\n  })();");
      assert.ok(bodyEnd > -1, "가지들을 body 로 묶지 않았다");
      assert.ok(
        fn.indexOf("{overlays}") > bodyEnd,
        "{overlays} 가 가지 안에 있다 - 가지가 바뀌면 언마운트됐다가 다시 마운트되어 지난 판정이 재생된다",
      );
    });

    it(`${name} 은 출구가 하나뿐이다`, () => {
      // 위 검사만으로는 **body 를 만든 뒤의 이른 return** 을 못 본다. 리뷰가
      // `})();` 와 마지막 return 사이에 `if (phase === "done") return <DoneCard/>`
      // 한 줄을 끼워 넣어 보니 이 파일의 검사가 전부 통과했다 - 세 번 난
      // 버그가 초록불 아래로 돌아오는 모양이다.
      //
      // 그래서 컴포넌트 본체의 최상위(두 칸 들여쓰기)만 떼어 본다. 훅은
      // 조건부로 부를 수 없으니 최상위의 분기는 사실상 이른 return 뿐이다.
      //
      // 처음에는 `if (` 와 `return` 만 셌다. 동적 테스트가 변이로 깨 보니
      // `if(` (공백 없음), 최상위 switch, `{ if (...) return }` 블록이 다
      // 통과했다. 분기를 만드는 문법을 전부 막는다.
      const start = code.indexOf("\nexport function ");
      const end = code.indexOf("\n}\n", start);
      const component = code.slice(start, end + 2);

      assert.equal(
        count(component, /\n {2}(?:if|switch|for|while|do|try)\b/g),
        0,
        "최상위에 분기가 있다 - 이른 return 이면 그 가지로 갈 때 연출이 언마운트된다",
      );
      assert.equal(
        count(component, /\n {2}\{/g),
        0,
        "최상위에 블록이 있다 - 안에 이른 return 을 숨길 수 있다",
      );
      assert.equal(
        count(component, /\n {2}return\b/g),
        1,
        "최상위 return 이 하나가 아니다",
      );
    });

    it(`${name} 의 마지막 return 은 정해진 모양 그대로다`, () => {
      // **모양을 글자째 못 박는다.** "{overlays} 를 담았는가" 만 보면 아래가
      // 전부 통과했다(동적 테스트의 변이). 셋 다 상태가 바뀔 때 overlays 가
      // 다시 마운트되어 지난 판정이 재생된다.
      //
      //     <div key={error}>{overlays}{body}</div>     key 가 바뀌면 통째로 새로 붙는다
      //     return error ? <p/> : <>{overlays}{body}</>  삼항의 한쪽 가지다
      //     <>{error ? <p/> : <>{overlays}{body}</>}</>  조건 안에 들었다
      //
      // 이 모양을 바꿔야 할 일이 생기면 연출이 가지 밖에 남는지 먼저 확인하고
      // 여기를 같이 고친다.
      const start = code.indexOf("\nexport function ");
      const end = code.indexOf("\n}\n", start);
      const component = code.slice(start, end + 2);

      assert.ok(
        component.endsWith(
          "\n  return (\n    <>\n      {overlays}\n      {body}\n    </>\n  );\n}",
        ),
        "마지막 return 이 <>{overlays}{body}</> 모양이 아니다",
      );
      // 다른 이름으로 받아 가지 안에서 한 번 더 그리는 것도 막는다
      // (`const layer = overlays`). 만드는 자리와 그리는 자리, 둘뿐이어야 한다.
      assert.equal(
        count(component, /\boverlays\b/g),
        2,
        "overlays 를 만드는 자리와 마지막 return 말고 다른 곳에서도 쓴다",
      );
    });

    it(`${name} 은 Reaction 을 overlays 안에서만 그린다`, () => {
      const overlaysAt = fn.indexOf("const overlays = (");
      const overlaysEnd = fn.indexOf("\n  );", overlaysAt);
      assert.ok(overlaysEnd > overlaysAt, "overlays 블록이 안 닫혔다");
      for (const tag of ["<Reaction", "<Burst"]) {
        const at = fn.indexOf(tag);
        assert.ok(at > overlaysAt && at < overlaysEnd, `${tag} 이 밖에 있다`);
      }
    });
  }
});

describe("어둡게 까는 것은 답한 뒤 멈추는 화면에서만", () => {
  /**
   * 기본값 없는 필수 prop 이라 타입검사가 "빠뜨리는 것" 은 막지만, **어느
   * 화면이 어느 쪽인지**는 타입이 모른다. 안 멈추는 화면에서 깔면 이 층이
   * pointer-events: none 이라 안 보이는 화면에서 다음 답을 고르게 된다.
   */
  for (const name of ["QuizBoard.tsx", "RoundBoard.tsx"]) {
    it(`${name} 은 깐다`, () => {
      assert.match(stripComments(read(name)), /<Reaction[^/]*\sdim\s*\/>/);
    });
  }

  for (const name of ["DailyStudyBoard.tsx", "ReviewBoard.tsx"]) {
    it(`${name} 은 안 깐다`, () => {
      assert.match(stripComments(read(name)), /<Reaction[^/]*dim=\{false\}/);
    });
  }
});

describe("연출은 끝나면 화면에서 걷힌다", () => {
  const css = read("..", "app", "globals.css");

  it("층 전체를 걷는 vx-out 이 있다", () => {
    // 이것이 없으면 사람이 화면 가운데에 박혀 다음 문제를 푸는 내내 서
    // 있다. 원본 키프레임의 마지막이 "무대 한가운데 서 있는 상태" 이고
    // animation-fill-mode: both 가 그 프레임을 붙들기 때문이다.
    assert.match(css, /@keyframes vx-out\b/);
    assert.match(css, /animation-name:\s*vx-out;/);
  });

  it("vx-out 을 animation 단축으로 적지 않는다", () => {
    // 단축은 안 적은 값을 초기화한다. 나중에 .vx 에 애니메이션을 하나 더
    // 얹는 사람이 단축으로 적으면 이 줄이 통째로 지워져 위 결함이 그대로
    // 돌아온다. 빌드는 통과하고 화면만 달라진다.
    assert.doesNotMatch(css, /\n\s*animation:\s*vx-out\b/);
  });

  it("무대는 정지점마다 opacity 를 적는다", () => {
    // 일부 키프레임에만 적으면 브라우저가 암묵적인 0% 프레임을 만들고 그
    // 둘 사이만 보간한다. 100% 에만 있었을 때 120ms 에 0.49 로 떨어져,
    // 닿는 순간(66%)의 판정색 전환이 opacity 0.012 로 일어나 안 보였다.
    const block = css.slice(css.indexOf("@keyframes vx-spot"));
    const body = block.slice(0, block.indexOf("\n}"));
    assert.equal(count(body, /opacity:/g), 4);
  });
});
