/**
 * /board/[kind] 가 종류마다 무엇을 하는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * weekly 는 /board 가 맡으므로 /board/weekly 는 /board 로 보낸다. 전에는
 * 404 였는데 generateMetadata 는 weekly 를 정상으로 받아서 탭 제목은
 * "이번 주 최고점" 인 채 본문만 "없는 순위표" 가 됐다. 모르는 종류는
 * 그대로 404 다.
 *
 * notFound·redirect 는 실제 Next 에서도 던진다. 같은 방식으로 던지는 대역을
 * 두어 어느 쪽으로 빠졌는지 잡는다. BoardScreen 이 끌고 오는 세션 모듈은
 * "server-only" 라 Next 밖에서 import 하면 터지므로 대역으로 바꾼다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";

class NotFound extends Error {}
class Redirect extends Error {
  constructor(readonly to: string) {
    super("NEXT_REDIRECT");
  }
}

mock.module("next/navigation", {
  namedExports: {
    notFound: () => {
      throw new NotFound();
    },
    redirect: (to: string) => {
      throw new Redirect(to);
    },
  },
});

mock.module("@/lib/session", {
  namedExports: {
    getToken: async () => null,
    withTokenOrGuest: async <T,>(
      token: string | null,
      call: (token?: string) => Promise<T>,
    ) => ({ value: await call(token ?? undefined), token }),
  },
});

const page = await import("./[kind]/page");
const BoardKindPage = page.default;

const visit = (kind: string) => BoardKindPage({ params: Promise.resolve({ kind }) });

describe("/board/[kind]", () => {
  it("weekly 는 /board 로 보낸다", async () => {
    await assert.rejects(visit("weekly"), (error) => {
      assert.ok(error instanceof Redirect, String(error));
      assert.equal(error.to, "/board");
      return true;
    });
  });

  for (const kind of ["nope", "WEEKLY", "weekly ", "all-time", "", "__proto__"]) {
    it(`모르는 종류 ${JSON.stringify(kind)} 는 404 다`, async () => {
      await assert.rejects(visit(kind), NotFound);
    });
  }

  for (const kind of ["all_time", "streak"]) {
    it(`${kind} 는 보내지 않고 그 순위표를 그린다`, async () => {
      const element = (await visit(kind)) as { props: { kind: string } };
      assert.equal(element.props.kind, kind);
    });
  }
});
