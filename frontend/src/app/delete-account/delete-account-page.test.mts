/**
 * 계정 삭제 안내(/delete-account)가 스토어 링크로 바로 열렸을 때 막히는 곳이
 * 없는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * legal-pages.test.mts 는 문구(앱 이름, 메일 주소)와 "버전 v" 가 없다는 것만
 * 본다. 여기서는 그 밖의 계약을 본다.
 *   - 버전 줄은 삭제 안내에서만 빠지고 처리방침·약관에는 그대로 남는다.
 *     LegalDoc 의 showVersion 기본값이 true 다.
 *   - 탭바는 /delete-account 에서만 숨는다. 앞부분이 같은 다른 주소에서는
 *     숨지 않는다(TabBar 의 정확 일치 규칙).
 *   - 본문의 내부 링크가 실제 있는 화면과 절을 가리킨다.
 *   - 처리방침에서 이 페이지로 가는 링크가 8절(권리 행사)에 있다.
 *   - 4절의 기간이 처리방침 3절과 어긋나지 않는다(페이지 주석이 요구한다).
 *   - 로그인 없이 열려야 하므로 서버에서 세션을 읽지 않는다.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, it, mock } from "node:test";
import { fileURLToPath } from "node:url";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** 대역 usePathname 이 돌려줄 경로. */
let pathname = "/";

mock.module("next/navigation", {
  namedExports: { usePathname: () => pathname },
});

// 여기서 볼 것은 주소뿐이다. next/link 는 브라우저 라우터를 기대한다.
mock.module("next/link", {
  defaultExport: (props: { href: string; children: ReactNode }) =>
    createElement("a", { href: props.href }, props.children),
});

const { DOC_VERSION, EFFECTIVE_DATE, LegalDoc } = await import(
  "../../components/LegalDoc"
);
const { TabBar } = await import("../../components/TabBar");
const { safeNext } = await import("../../lib/routes");
const { default: TermsPage } = await import("../terms/page");
const { default: PrivacyPage } = await import("../privacy/page");
const deleteModule = await import("./page");
const DeleteAccountPage = deleteModule.default;

const html = {
  privacy: renderToStaticMarkup(createElement(PrivacyPage)),
  terms: renderToStaticMarkup(createElement(TermsPage)),
  deleteAccount: renderToStaticMarkup(createElement(DeleteAccountPage)),
};

const APP_DIR = fileURLToPath(new URL("..", import.meta.url));

/**
 * src/app 아래 page.tsx 로 실제 열리는 주소들. (auth) 같은 묶음 폴더는
 * 주소에 나타나지 않으므로 뺀다.
 */
function appRoutes(): Set<string> {
  const routes = new Set<string>();
  for (const entry of readdirSync(APP_DIR, { recursive: true })) {
    const file = String(entry).replace(/\\/g, "/");
    if (!/(^|\/)page\.tsx$/.test(file)) continue;
    const segments = file
      .split("/")
      .slice(0, -1)
      .filter((s) => !/^\(.*\)$/.test(s));
    routes.add("/" + segments.join("/"));
  }
  return routes;
}

/** 렌더 결과의 a 태그 href 전부. */
function hrefs(markup: string): string[] {
  return [...markup.matchAll(/<a [^>]*href="([^"]*)"/g)].map((m) =>
    m[1].replace(/&amp;/g, "&"),
  );
}

/** id 로 찾은 section 하나의 마크업. */
function section(markup: string, id: string): string {
  const match = markup.match(
    new RegExp(`<section[^>]*id="${id}"[^>]*>([\\s\\S]*?)</section>`),
  );
  assert.ok(match, `section#${id} 이 없다`);
  return match[1];
}

const VERSION_LINE = `버전 ${DOC_VERSION} · 시행일 ${EFFECTIVE_DATE}`;

describe("버전 줄", () => {
  it("처리방침과 약관에는 버전과 시행일이 그대로 있다", () => {
    // showVersion 기본값이 false 로 뒤집히면 동의 문서에서 버전이 사라져
    // 누가 어느 판에 동의했는지 화면으로 확인할 길이 없다.
    assert.ok(html.privacy.includes(VERSION_LINE), "처리방침에 버전 줄이 없다");
    assert.ok(html.terms.includes(VERSION_LINE), "약관에 버전 줄이 없다");
  });

  it("계정 삭제 안내에는 버전도 시행일도 없다", () => {
    assert.ok(!html.deleteAccount.includes(DOC_VERSION), "버전이 보인다");
    assert.ok(!html.deleteAccount.includes(EFFECTIVE_DATE), "시행일이 보인다");
    assert.doesNotMatch(html.deleteAccount, /시행일/);
  });

  it("LegalDoc 은 showVersion 을 빼면 보이고 false 일 때만 숨긴다", () => {
    const base = {
      title: "t",
      sections: [{ id: "a", title: "1. a", body: "b" }],
      other: { href: "/privacy", label: "x" },
    };
    const render = (extra: object) =>
      renderToStaticMarkup(createElement(LegalDoc, { ...base, ...extra }));
    assert.ok(render({}).includes(VERSION_LINE));
    assert.ok(render({ showVersion: true }).includes(VERSION_LINE));
    assert.ok(!render({ showVersion: false }).includes(VERSION_LINE));
  });
});

describe("탭바", () => {
  function tabBar(path: string): string {
    pathname = path;
    return renderToStaticMarkup(createElement(TabBar));
  }

  it("/delete-account 에서는 그리지 않는다", () => {
    assert.equal(tabBar("/delete-account"), "");
  });

  it("처리방침·약관에서도 여전히 그리지 않는다", () => {
    assert.equal(tabBar("/privacy"), "");
    assert.equal(tabBar("/terms"), "");
  });

  it("앞부분만 같은 다른 주소에서는 그린다", () => {
    // 접두어로 거르면 없는 주소(404)에서도 탭바가 사라져 막다른 화면이 된다.
    for (const path of [
      "/delete-account/x",
      "/delete-accounts",
      "/Delete-Account",
      "/delete",
      "/profile/delete-account",
    ]) {
      assert.match(tabBar(path), /data-tabbar/, path);
    }
  });
});

describe("계정 삭제 안내의 링크", () => {
  const routes = appRoutes();
  const links = hrefs(html.deleteAccount);

  it("앱 안 주소는 모두 실제 있는 화면이다", () => {
    const internal = links.filter((h) => h.startsWith("/"));
    assert.ok(internal.length >= 4, `내부 링크 ${internal.length}개`);
    for (const href of internal) {
      const path = href.split(/[?#]/)[0];
      assert.ok(routes.has(path), `${href} 의 화면(${path})이 없다`);
    }
  });

  it("로그인 링크는 로그인 뒤 내정보로 돌아온다", () => {
    const login = links.find((h) => h.startsWith("/login"));
    assert.ok(login, "로그인 링크가 없다");
    const next = new URL(login, "http://x").searchParams.get("next");
    assert.equal(next, "/profile");
    // 로그인 액션이 거르는 함수를 그대로 통과해야 실제로 내정보로 간다.
    assert.equal(safeNext(next), "/profile");
  });

  it("처리방침 링크의 절이 처리방침에 있다", () => {
    const withHash = links.filter((h) => h.startsWith("/privacy#"));
    assert.ok(withHash.length >= 1, "처리방침 절 링크가 없다");
    for (const href of withHash) {
      const id = href.split("#")[1];
      assert.match(html.privacy, new RegExp(`<section[^>]*id="${id}"`), href);
    }
  });

  it("'처리방침 3·4절' 이라고 부른 링크가 정말 3절로 간다", () => {
    const id = links.find((h) => h.startsWith("/privacy#"))!.split("#")[1];
    assert.match(section(html.privacy, id), /<h2[^>]*>3\. /);
  });

  it("같은 페이지 목차 링크가 모두 이 페이지의 절을 가리킨다", () => {
    const local = links.filter((h) => h.startsWith("#"));
    assert.ok(local.length >= 4, `목차 링크 ${local.length}개`);
    for (const href of local) {
      assert.match(html.deleteAccount, new RegExp(`id="${href.slice(1)}"`), href);
    }
  });
});

describe("처리방침과의 연결", () => {
  it("처리방침 8절(권리 행사)에서 이 페이지로 링크한다", () => {
    const rights = section(html.privacy, "rights");
    assert.match(rights, /<h2[^>]*>8\. /);
    assert.match(rights, /href="\/delete-account"/);
  });

  it("4절의 기간과 처리 기한이 처리방침과 같다", () => {
    // 페이지 주석: "4절의 기간은 처리방침 3·4절을 옮긴 것이라 그쪽을 고치면
    // 여기도 고친다". 한쪽만 고쳐지면 두 문서가 다른 기간을 말한다.
    const retention = section(html.privacy, "retention");
    for (const phrase of ["Vercel 1시간", "Railway\\s+7일", "30일 안"]) {
      const re = new RegExp(phrase);
      assert.match(html.deleteAccount, re, `삭제 안내에 ${phrase} 없음`);
      assert.match(retention, re, `처리방침 3절에 ${phrase} 없음`);
    }
    assert.match(html.deleteAccount, /10일 안에/);
    assert.match(section(html.privacy, "rights"), /10일 안에/);
  });
});

describe("로그인 없이 열린다", () => {
  const source = readFileSync(
    new URL("./page.tsx", import.meta.url),
    "utf8",
  );

  it("서버에서 세션·쿠키를 읽거나 로그인으로 보내지 않는다", () => {
    assert.doesNotMatch(source, /getCurrentUser|next\/headers|cookies\(|redirect\(/);
    assert.doesNotMatch(source, /^["']use client["']/m);
  });

  it("브라우저 탭 제목에 계정 삭제가 들어간다", () => {
    const title = String(deleteModule.metadata?.title ?? "");
    assert.match(title, /계정 삭제/);
  });
});
