/**
 * 처리방침·약관·계정 삭제 안내와 가입·내정보 입력칸의 말 바꾸기를 렌더해서 본다.
 *
 * 실행: cd frontend && npx tsx --test --experimental-test-module-mocks src/app/privacy/policy-wording-dynamic.test.mts
 *
 * 계약:
 *   - "보여지는 이름" 은 "닉네임", "프로필 그림" 은 "프로필 사진" 이다. 옛 말이 화면 글자에도,
 *     속성(aria-label·title·alt·placeholder)에도 남지 않는다.
 *   - 입력칸은 글자만 바뀌었다. name="display_name", maxLength 12 는 그대로다.
 *   - 처리방침 14절은 공고일·시행일과 이번 버전의 바뀐 내용 세 항목뿐이다. 앞 버전 이력은
 *     "이전 버전" 줄까지 모두 지웠다(2026-11-22 사용자 결정). v2·v3·v4 가 다시 나오지 않는다.
 *   - 14절 밖의 본문에 남는 날짜는 버전 줄, 3절 백업 시작일, 7절 v5 공고일 셋뿐이다.
 *   - 처리방침 3·4절과 계정 삭제 안내 4절의 기간 숫자가 서로 맞다.
 *   - 문장을 줄여도 사실은 남는다: 요청 횟수 1분·1시간 단위와 최대 1시간, 관리자 화면
 *     로그인 세기, 문제풀기 6시간 10분, 사목의 요청 방식, 14절의 11월 21일 세기 문장.
 *     해시값을 "되돌릴 수 없다" 로 과장하지 않는다.
 *
 * v5 전용 부분이 있다. 14절, 14절 밖 본문의 날짜, 버전 줄, 14절 Sentry 항목은 v5 의 날짜와
 * 문장을 글자로 박아 두어 DOC_VERSION 이 v5 가 아니면 건너뛴다. 다음 개정 때 이 파일의 v5 절을
 * 지우거나 새 버전에 맞춘다. 옛 말, 입력칸 속성, 기간 일치, 줄이면 안 되는 사실(14절 제외),
 * 해시 과장, 화면 문구는 버전과 무관해 늘 돈다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// next/link 는 브라우저 라우터를 기대한다. 여기서 볼 것은 글자뿐이다.
mock.module("next/link", {
  defaultExport: (props: { href: string; children: ReactNode }) =>
    createElement("a", { href: props.href }, props.children),
});
// ProfileForm 의 useUnsavedGuard 가 부른다.
mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({ push() {}, replace() {}, back() {}, refresh() {}, prefetch() {} }),
  },
});
// AuthForm 의 구글 버튼과 게스트 시트가 부르는 서버 액션. 실제 파일은 서버 전용 모듈을 불러 읽히지 않는다.
mock.module("@/app/(auth)/google-actions", {
  namedExports: {
    prepareGoogleButton: async () => null,
    googleCredentialAction: async () => {},
  },
});
mock.module("@/app/start/actions", {
  namedExports: { continueAsGuestAction: async () => {} },
});

const { default: PrivacyPage } = await import("./page");
const { default: TermsPage } = await import("../terms/page");
const { default: DeleteAccountPage } = await import("../delete-account/page");
const { AuthForm } = await import("../../components/AuthForm");
const { ProfileForm } = await import("../../components/ProfileForm");
const { GoogleNameNote } = await import("../(auth)/ConsentChecks");
const { DOC_VERSION } = await import("../../components/LegalDoc");

// v5 의 날짜·14절 문장을 글자로 박은 검사는 v5 일 때만 돈다. 다음 개정 때 지우거나 맞춘다.
const IS_V5 = DOC_VERSION === "v5";
const V5_ONLY = { skip: !IS_V5 };

const noop = async () => ({ error: null });

const html = {
  privacy: renderToStaticMarkup(createElement(PrivacyPage)),
  terms: renderToStaticMarkup(createElement(TermsPage)),
  "delete-account": renderToStaticMarkup(createElement(DeleteAccountPage)),
  "가입 화면": renderToStaticMarkup(
    createElement(AuthForm, { mode: "signup", action: noop as never, googleFailed: false }),
  ),
  "로그인 화면": renderToStaticMarkup(
    createElement(AuthForm, { mode: "login", action: noop as never, googleFailed: false }),
  ),
  "내정보 화면": renderToStaticMarkup(
    createElement(ProfileForm, {
      action: async () => ({}),
      initialName: "초롱",
      initialAvatar: "",
      shown: { type: "preset", key: "a1" },
      googlePicture: "",
      uploadPhoto: async () => ({}),
      deletePhoto: async () => ({}),
      uploadedPhoto: "",
    } as never),
  ),
  "구글 이름 안내": renderToStaticMarkup(createElement(GoogleNameNote)),
};

/** 화면에 보이는 글자. JSX 줄바꿈은 공백 하나로 접힌다. */
function text(markup: string): string {
  return markup
    .replace(/<[^>]+>/g, " ")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");
}

function section(markup: string, id: string): string {
  const body = markup.match(new RegExp(`<section[^>]*id="${id}"[^>]*>([\\s\\S]*?)</section>`))?.[1];
  assert.ok(body, `${id} 절을 못 찾았다`);
  return body;
}

/** 절 안의 li 를 글자로. 중첩 목록은 없다. */
function items(markup: string): string[] {
  return [...markup.matchAll(/<li[^>]*>([\s\S]*?)<\/li>/g)].map((m) => text(m[1]).trim());
}

const privacyText = text(html.privacy);
const changes = section(html.privacy, "changes");
const changesText = text(changes);
const bodyText = text(html.privacy.replace(/<section[^>]*id="changes"[\s\S]*?<\/section>/, ""));

// ---------------------------------------------------------------------------

describe("옛 말이 남지 않는다", () => {
  const OLD = [/보여지/, /프로필\s*그림/];

  for (const [name, markup] of Object.entries(html)) {
    it(`${name}: 보이는 글자와 속성 모두에 "보여지는"·"프로필 그림" 이 없다`, () => {
      for (const re of OLD) {
        assert.doesNotMatch(text(markup), re, `${name} 글자`);
        assert.doesNotMatch(markup, re, `${name} 속성`);
      }
    });
  }

  it("세 문서는 새 말을 실제로 쓴다(지우기만 하고 비워 두지 않았다)", () => {
    for (const name of ["privacy", "terms", "delete-account"] as const) {
      assert.match(text(html[name]), /닉네임/, name);
    }
    assert.match(privacyText, /닉네임·프로필 사진·점수를 순위표에/);
    assert.match(text(html.terms), /제7조 \(닉네임과 프로필 사진\)/);
    assert.match(text(html.terms), /표시되는 이름과 사진을 말합니다/);
  });

  it("약관 제7조 1항: 닉네임 최대 12자, 프로필 사진은 아바타·올린 사진·구글 사진 중 하나", () => {
    // 1항을 두 문장으로 나누며 "무엇 중 하나" 가 빠지기 쉽다. 세 가지가 모두 남아야 한다.
    const first = items(section(html.terms, "art7"))[0] ?? "";
    assert.match(first, /^회원은 닉네임\(최대 12자\)과 프로필 사진을 정할 수 있습니다\./);
    assert.match(
      first,
      /프로필 사진은 제공되는 아바타, 직접 올린 사진, 구글 프로필 사진 중 하나입니다\.$/,
    );
  });

  it("약관 목차가 바뀐 제7조 제목으로 art7 을 가리킨다", () => {
    assert.match(html.terms, /<a href="#art7"[^>]*>제7조 \(닉네임과 프로필 사진\)<\/a>/);
    assert.match(html.terms, /<section[^>]*id="art7"/);
  });
});

describe("입력칸은 글자만 바뀌었다", () => {
  it("가입 화면: 닉네임 label 이 display_name 칸을 가리키고 maxLength 12·nickname 자동완성이 그대로다", () => {
    const signup = html["가입 화면"];
    const input = signup.match(/<input[^>]*name="display_name"[^>]*>/)?.[0];
    assert.ok(input, "display_name 칸이 없다");
    assert.match(input, /maxLength="12"/);
    assert.match(input, /type="text"/);
    assert.match(input, /autoComplete="nickname"/);
    const id = input.match(/id="([^"]+)"/)?.[1];
    assert.ok(id, "칸에 id 가 없다");
    const label = signup.match(new RegExp(`<label[^>]*for="${id}"[^>]*>([\\s\\S]*?)</label>`))?.[1];
    assert.ok(label, "칸을 가리키는 label 이 없다");
    // 가입 화면 label 에는 "(선택)" 표시가 붙는다. 이름 자리는 닉네임이다.
    assert.match(text(label).trim(), /^닉네임(?: \(선택\))?$/);
    assert.match(text(signup), /순위표에 뜰 닉네임입니다\. 비워두면 알아서 지어드립니다\./);
  });

  it("로그인 화면에는 닉네임 칸이 없다", () => {
    assert.doesNotMatch(html["로그인 화면"], /name="display_name"/);
    assert.doesNotMatch(text(html["로그인 화면"]), /닉네임/);
  });

  it("내정보 화면: label 이 닉네임이고 칸은 display_name·maxLength 12·required 그대로다", () => {
    const profile = html["내정보 화면"];
    const label = profile.match(/<label[^>]*for="display_name"[^>]*>([\s\S]*?)<\/label>/)?.[1];
    assert.ok(label);
    assert.equal(text(label).trim(), "닉네임");
    const input = profile.match(/<input[^>]*id="display_name"[^>]*>/)?.[0];
    assert.ok(input);
    assert.match(input, /name="display_name"/);
    assert.match(input, /maxLength="12"/);
    assert.match(input, /required=""/);
    assert.match(input, /value="초롱"/);
  });
});

describe("처리방침 14절", V5_ONLY, () => {
  const lis = items(changes);

  it("공고일·시행일, 바뀐 내용 세 항목 - 다섯 항목뿐이다", () => {
    assert.equal(lis.length, 5, lis.join("\n"));
    assert.equal(lis[0], "공고일: 2026년 11월 21일");
    assert.equal(lis[1], "시행일: 2026년 11월 28일");
    assert.match(lis[2], /^바뀐 내용: /);
  });

  it("앞 버전 이력이 남지 않는다", () => {
    assert.equal(changesText.match(/바뀐 내용/g)?.length, 1);
    for (const re of [/이전 버전/, /다른 곳은/, /달랐던/, /바꾼\s*내용/, /공고,/, /11월 1[23]일/, /나머지 문장은/, /v[234]\b/]) {
      assert.doesNotMatch(changesText, re);
    }
  });

  it("시행 전부터 하고 있는 세 가지의 시작일은 남는다", () => {
    assert.match(changesText, /Sentry 로 보내기는 2026년 11월 20일부터 하고 있습니다/);
    assert.match(changesText, /백업은 시행일을 기다리지 않고 2026년 11월 21일부터 하고 있습니다/);
    assert.match(changesText, /구글 가입·로그인 시도도[^.]*IP 주소의 해시값으로/);
    assert.match(changesText, /시행일을 기다리지 않고 2026년 11월 22일부터 합니다/);
  });
});

describe("처리방침 본문(14절 밖)의 날짜", V5_ONLY, () => {
  it("남는 날짜는 버전 줄, 3절 백업 시작일, 7절 v5 공고일 셋뿐이다", () => {
    const found = [...bodyText.matchAll(/(?:\d{4}년\s*)?\d{1,2}월\s*\d{1,2}일[^ ]*\s*\S+/g)].map((m) => m[0]);
    assert.deepEqual(found, [
      "2026년 11월 28일 DeVoca",
      "2026년 11월 21일부터 운영자가",
      "2026년 11월 21일 전에",
    ]);
  });

  it("버전 줄은 버전 v5 · 시행일 2026년 11월 28일 이다", () => {
    assert.match(privacyText, /버전 v5 · 시행일 2026년 11월 28일/);
    assert.equal(privacyText.match(/버전 v\d/g)?.length, 1);
  });

  it("3절 백업 시작일과 7절 공고일이 제 절에 있다", () => {
    assert.match(text(section(html.privacy, "retention")), /데이터베이스 백업: 2026년 11월 21일부터 운영자가 매일/);
    assert.match(text(section(html.privacy, "transfer")), /v5 를 공고한 2026년 11월 21일 전에 가입한 회원/);
  });

  it("지난 시작일·옛 버전 이름이 본문에 없다", () => {
    for (const re of [/11월 19일/, /11월 22일/, /11월 13일/, /11월 20일/, /v[234]\b/]) {
      assert.doesNotMatch(bodyText, re);
    }
  });

  it("약관에 남은 날짜는 버전 줄과 부칙의 약관 시행일뿐이다", () => {
    const found = [...text(html.terms).matchAll(/\d{4}년\s*\d{1,2}월\s*\d{1,2}일/g)].map((m) => m[0]);
    assert.deepEqual(found, ["2026년 11월 9일", "2026년 11월 9일"]);
  });
});

describe("계정 삭제 안내의 날짜", () => {
  // 버전 줄을 띄우지 않는 문서라(showVersion={false}) 버전이 바뀌어도 늘 성립한다.
  it("날짜와 버전 표시가 하나도 없다", () => {
    assert.doesNotMatch(text(html["delete-account"]), /\d{1,2}월\s*\d{1,2}일|버전 v/);
  });
});

describe("처리방침 3·4절과 계정 삭제 안내 4절의 기간", () => {
  const retention = items(section(html.privacy, "retention"));
  const destruction = items(section(html.privacy, "destruction"));
  const kept = items(section(html["delete-account"], "kept"));

  const pick = (list: string[], re: RegExp): string => {
    const hit = list.filter((s) => re.test(s));
    assert.equal(hit.length, 1, `${re} 에 맞는 항목이 ${hit.length}개다:\n${list.join("\n")}`);
    return hit[0];
  };
  const durations = (s: string) => [...s.matchAll(/\d+\s*(?:일|시간|분)/g)].map((m) => m[0]).sort();

  // [항목, 삭제 안내에서 찾는 말, 처리방침 3·4절에서 찾는 말]
  const PAIRS: Array<[string, RegExp, string[], RegExp]> = [
    ["안내 메일", /Gmail 보낸편지함/, retention, /Gmail 보낸편지함/],
    ["호스팅 업체 접속 로그", /호스팅 업체.*접속 로그/, retention, /^호스팅 업체 접속 로그/],
    ["서버 오류 기록", /^서버 오류 기록/, retention, /^서버 오류 기록/],
    ["Sentry 오류 기록", /^오류 알림 서비스 Sentry/, retention, /^Sentry 로 보낸 오류 기록/],
    ["데이터베이스 백업", /^운영자가 매일 만드는 데이터베이스 백업/, retention, /^데이터베이스 백업/],
    ["브라우저에 남은 사진", /브라우저에 남은 사진/, destruction, /브라우저에는 사진이/],
  ];

  for (const [label, kRe, list, pRe] of PAIRS) {
    it(`${label}: 기간 숫자가 같다`, () => {
      const k = durations(pick(kept, kRe));
      const p = durations(pick(list, pRe));
      assert.ok(k.length > 0, `${label}: 삭제 안내에 기간이 없다`);
      for (const d of k) assert.ok(p.includes(d), `${label}: 삭제 안내의 ${d} 가 처리방침에 없다 (${p.join(", ")})`);
    });
  }

  it("백업 기간은 처리방침 3절·4절·14절에서 모두 14일이다", () => {
    for (const s of [
      pick(retention, /^데이터베이스 백업/),
      pick(destruction, /백업에는 최대/),
      pick(destruction, /운영자가 만든 데이터베이스 백업/),
      // 14절의 백업 문장은 v5 의 바뀐 내용이라 다음 개정 때 빠진다.
      ...(IS_V5 ? [changesText] : []),
    ]) {
      // 백업을 말하는 문장 안의 일수는 모두 14일이다(같은 항목의 "사진 최대 7일" 은 백업이 아니다).
      const backup = s.split(/(?<=\.)\s/).filter((x) => x.includes("백업"));
      assert.ok(backup.length > 0, s);
      for (const x of backup) {
        const days = x.replace(/\d{4}년\s*\d{1,2}월\s*\d{1,2}일/g, "").match(/\d+일/g) ?? [];
        for (const d of days) assert.equal(d, "14일", x);
      }
    }
  });

  it("로그인 토큰·쿠키는 30일이다", () => {
    assert.match(pick(retention, /^로그인 토큰/), /발급 후 30일/);
    assert.match(pick(retention, /^로그인 쿠키/), /30일/);
  });

  // 문장을 줄이다 처리방침 3절에서 "최대 1시간" 이 빠진 적이 있다. 보관 기간이라 3절과
  // 계정 삭제 안내 4절에 같은 숫자로 남아야 한다(3절 위 주석: 여기를 고치면 그쪽도 고친다).
  it("요청 횟수 제한 기록: 삭제 안내의 최대 1시간이 처리방침 3절에도 있다", () => {
    const k = durations(pick(kept, /^요청을 너무 자주/));
    const p = durations(pick(retention, /^요청 횟수 제한 기록/));
    assert.deepEqual(k, ["1시간"]);
    for (const d of k) assert.ok(p.includes(d), `처리방침 3절에 없다: ${d}`);
  });
});

// ---------------------------------------------------------------------------
// 문장을 줄이다 빠졌다가 되살린 사실들. 다시 줄일 때 또 빠지기 쉬운 자리다.
// ---------------------------------------------------------------------------

describe("처리방침에서 줄이면 안 되는 사실", () => {
  const items2 = items(section(html.privacy, "items"));
  const retention = items(section(html.privacy, "retention"));
  const pickOne = (list: string[], re: RegExp): string => {
    const hit = list.filter((s) => re.test(s));
    assert.equal(hit.length, 1, `${re} 에 맞는 항목이 ${hit.length}개다:\n${list.join("\n")}`);
    return hit[0];
  };

  it("3절 요청 횟수 제한 기록: 1분·1시간 단위, 관리자 화면 로그인, 서버 비밀값을 섞은 해시값, 최대 1시간", () => {
    const s = pickOne(retention, /^요청 횟수 제한 기록/);
    assert.match(s, /1분 또는 1시간 단위/);
    assert.match(s, /관리자 화면 로그인 시도/);
    assert.match(s, /접속한 IP 주소/);
    assert.match(s, /서버 비밀값을 섞은 해시값/);
    assert.match(s, /제한 시간\(최대 1시간\)/);
    assert.match(s, /회원 번호/);
  });

  it("3절 문제풀기 진행 기록: 유효 시간 10분, 복습은 최대 6시간 10분", () => {
    const s = pickOne(retention, /^문제풀기 진행 기록/);
    assert.match(s, /유효 시간\(10분, 복습은 최대 6시간 10분\)/);
  });

  it("2절 라목: IP 주소를 서버 비밀값을 섞은 해시값으로 바꿔 둔다", () => {
    const s = pickOne(items2, /시도 횟수를 세기 위해 접속한 IP 주소/);
    assert.match(s, /서버 비밀값을 섞은 해시값으로 바꿔/);
  });

  it("2절 사목: 서버 오류 기록과 오류 알림 메일 둘 다 요청 방식을 적는다", () => {
    const record = pickOne(items2, /^서버가 처리하지 못한 오류가 나면/);
    assert.match(record, /코드 위치, 요청 방식, 요청 주소, 오류 메시지/);
    const mail = pickOne(items2, /^운영자에게 가는 오류 알림 메일/);
    assert.match(mail, /코드 위치, 요청 방식,/);
    assert.match(mail, /오류 메시지는 넣지 않습니다/);
  });

  it("14절 Sentry 항목: 이메일 1시간 세기와 관리자 화면 로그인 세기를 2026년 11월 21일부터 한다고 적는다", V5_ONLY, () => {
    const s = pickOne(items(changes), /^바뀐 내용: /);
    assert.match(s, /이메일 로그인 시도를 1시간 단위로도 세고/);
    assert.match(s, /관리자 화면 로그인 시도도 이메일 해시값으로 셉니다/);
    assert.match(s, /둘 다 2026년 11월 21일부터 하고 있습니다/);
    // Sentry 시작일과 섞이지 않는다.
    assert.ok(s.indexOf("11월 20일") < s.indexOf("관리자 화면"), s);
  });

  it("해시값을 '되돌릴 수 없다'·'알아볼 수 없다' 로 과장하지 않는다(세 문서 모두)", () => {
    // 서버 비밀값을 섞은 해시값은 비밀값을 가진 쪽이 대조할 수 있다. IP 주소처럼 경우의 수가
    // 적은 값은 더 그렇다. 약관 제10조의 "삭제되며 되돌릴 수 없습니다" 는 해시 얘기가 아니다.
    for (const name of ["privacy", "terms", "delete-account"] as const) {
      for (const sentence of text(html[name]).split(/(?<=[.)])\s/)) {
        if (!sentence.includes("해시")) continue;
        assert.doesNotMatch(sentence, /되돌릴 수 없|되돌리기 어려|알아볼 수 없|복원할 수 없/, `${name}: ${sentence}`);
      }
    }
  });
});

describe("이름을 가리키던 화면 문구", () => {
  it("내정보 안내가 닉네임으로 말한다", () => {
    assert.match(
      text(html["내정보 화면"]),
      /순위표에 뜰 닉네임입니다\. 남이 쓰는 닉네임은 쓸 수 없습니다\./,
    );
  });

  it("구글 가입 안내: 구글 이름이 보이고 내정보에서 닉네임이나 아바타를 바꾼다", () => {
    const t = text(html["구글 이름 안내"]).trim();
    assert.match(t, /구글 이름과 사진이 보입니다/);
    assert.match(t, /내정보에서 닉네임이나 아바타를 바꿀 수 있습니다/);
  });
});
