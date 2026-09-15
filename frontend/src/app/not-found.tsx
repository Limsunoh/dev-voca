import type { Metadata } from "next";
import Link from "next/link";

import { routes } from "@/lib/routes";

/**
 * 탭·방문기록에 남는 제목. **없으면 정상 화면과 구별이 안 된다** - 루트
 * layout 의 `"devvoca"` 가 그대로 뜬다.
 *
 * 형제 not-found 셋도 같은 상태인데 이번에는 루트만 고친다. 셋은 한 문구로
 * 묶일 것이 아니라서다 - 그쪽은 `notFound()` 로 오는 자리라 위 세그먼트
 * 이름을 쓰는 것이 맞고(`단어장 | devvoca` 계열), 루트만 속한 세그먼트가
 * 없다.
 *
 * **같이 고칠 것이 따로 있다.** `learn/words/[id]/page.tsx:22` 와 문장 쪽
 * 짝이 `if (!word) return { title: ... }` 로 제목을 정하는데 35행의
 * `notFound()` 가 그 결과를 버린다 - 화면에 뜬 적 없는 문구다. 그 두 줄과
 * `learn/` not-found 둘은 한 이야기라 묶어서 다룬다.
 *
 * 문구는 아래 h1 과 같게 둔다. 화면 이름이 아니라 상태라서 `없는 주소` 로
 * 줄이지 않았다 - 방문기록에서 그런 화면이 있는 것처럼 읽힌다.
 */
export const metadata: Metadata = { title: "없는 주소입니다 | devvoca" };

/**
 * 어디에도 없는 주소로 들어왔을 때.
 *
 * 이 파일이 없으면 Next 기본 404 가 뜬다 - 흰 바탕에 영어로
 * "This page could not be found" 다. 한국어 화면을 쓰는 사용자에게
 * 그것만 보이면 서비스가 죽은 것으로 읽힌다.
 *
 * **도메인별 not-found 와 다른 점은 돌아갈 곳이다.** 단어·문장 쪽은 그
 * 목록으로 보내면 되지만(`learn/words/not-found.tsx`), 여기는 사용자가
 * 어디서 왔는지 알 수 없다. 그래서 홈으로 보낸다 - 로그인·게스트를 아직
 * 안 고른 사람은 홈이 다시 `/start` 로 보내주므로 막다르지 않다.
 *
 * **화면을 채우고 문구를 가로·세로 가운데 둔다.** not-found 넷 중 `board/` 는
 * 그렇게 하고 `learn/` 둘은 안 하는데, 이쪽은 `board/` 를 따른다 - `learn/` 은
 * 목록 화면에서 `notFound()` 로 떨어지는 자리라 위에 문맥이 남지만, 루트
 * 404 는 **화면에 이것뿐**이다. 홈이 같은 상황을 두고 이미 판단해 뒀다
 * (`page.tsx:472` - "실패하면 아래에 붙을 목록도 없어서 화면이 정말로
 * 비고, 그때는 문구가 가운데 있는 편이 낫다").
 *
 * **폭도 `board/` 를 따라 `max-w-2xl` 이다.** 저장소에서 폭이 갈리는 기준은
 * 화면 종류가 아니라 정렬이다 - `flex-1 justify-center` 로 가운데 두는 쪽은
 * 전부 좁고(`board/` 672px, `test/daily`·`test/review` 448px), `max-w-3xl`
 * (768px)은 왼쪽 정렬 문서형인 `learn/` 둘이 쓴다. 1280 에서 가운데 정렬로
 * 768px 을 쓰면 제목에서 버튼까지 시선이 형제들보다 눈에 띄게 멀다.
 */
export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 py-10 text-center">
      <h1
        style={{
          fontSize: "var(--text-2xl)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: "var(--foreground)",
        }}
      >
        없는 주소입니다
      </h1>
      <p className="mt-2" style={{ color: "var(--text-muted)" }}>
        주소를 잘못 입력했거나, 페이지가 옮겨졌을 수 있습니다.
      </p>

      {/* 이 화면의 코랄 하나. 갈 곳이 홈뿐이라 양보할 상대가 없다
          (`globals.css` - "한 화면에 코랄 버튼은 하나만 둔다"). `learn/` 의
          not-found 둘과 `test/daily/page.tsx` 가 같은 자리에서 같은 선택을
          했다.

          **형제를 색으로 판단하면 어긋난다.** `board/not-found.tsx` 가 흰
          알약인 것은 규칙이 달라서가 아니라 그쪽에 순위표 세 갈래라는 양보
          대상이 있어서다. `test/daily` 와 `test/review` 는 홈 링크 하나뿐인
          같은 자리인데 색이 갈린다 - `850e995` 에서 갈렸고 그전에는 두
          `Link` 가 공백까지 같았다. 둘 중 하나를 선례로 집으면 반대쪽과
          어긋난다.

          **div 로 한 겹 싸는 것이 필요하다.** `flex-col` 의 자식은 cross-axis
          stretch 를 받고 `display` 도 블록으로 바뀌어, `inline-flex` 가
          shrink-to-fit 을 잃고 화면 폭을 다 먹는다(390 에서 실측 358px).
          블록 래퍼가 그 stretch 를 받아 주고 안의 알약은 제 폭을 지키며
          위 `text-center` 로 가운데 놓인다. `board/not-found.tsx` 와
          `test/daily/page.tsx` 도 같은 모양이다. */}
      <div className="mt-6">
        <Link
          href={routes.home}
          className="dv-btn inline-flex items-center rounded-full px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              background: "var(--coral)",
              color: "var(--text-on-color)",
              minHeight: "var(--hit-min)",
              fontWeight: "var(--weight-black)",
              letterSpacing: "var(--tracking-tight)",
              // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
        >
          홈으로 가기
        </Link>
      </div>
    </main>
  );
}
