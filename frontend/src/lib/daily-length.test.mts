/**
 * 하루 공부량 값이 백엔드 일일공부 길이와 같은지 검증.
 *
 * 실행: cd frontend && npm test
 *
 * 프론트(lib/daily-length.ts)와 백엔드(apps/learning/models.py 의 StudyLength)가
 * 같은 세 값을 따로 들고 있다. 한쪽만 바꾸면 처음 묻는 화면이 백엔드가 모르는
 * 값을 저장하려다 400 을 받거나, 백엔드의 새 길이가 화면에 안 나온다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { DAILY_LENGTHS, dailyLengthLabel, isDailyLength } from "./daily-length";

const HERE = dirname(fileURLToPath(import.meta.url));
const MODELS = join(HERE, "../../../backend/apps/learning/models.py");

/** StudyLength 클래스 본문의 `NAME = "값", "이름"` 줄들. */
function backendLengths(): [string, string][] {
  const source = readFileSync(MODELS, "utf8");
  const start = source.indexOf("class StudyLength(");
  assert.notEqual(start, -1, "StudyLength 를 못 찾았다");
  const body = source.slice(start, source.indexOf("\n\n\n", start));
  return [...body.matchAll(/^\s+[A-Z_]+ = "([^"]+)", "([^"]+)"/gm)].map((m) => [m[1], m[2]]);
}

describe("하루 공부량", () => {
  it("값과 이름이 백엔드 StudyLength 와 같다", () => {
    const backend = backendLengths();
    assert.ok(backend.length >= 3, `백엔드 길이를 읽지 못했다: ${backend.length}`);
    assert.deepEqual(
      DAILY_LENGTHS.map((one) => [one.value, one.label]),
      backend,
    );
  });

  it("아는 값만 받는다", () => {
    for (const ok of ["5m", "10m", "30m"]) assert.equal(isDailyLength(ok), true, ok);
    for (const bad of ["", "15m", "5", "10M", " 5m", null, undefined, 10]) {
      assert.equal(isDailyLength(bad), false, String(bad));
    }
  });

  it("이름을 돌려주고 모르는 값은 null", () => {
    assert.equal(dailyLengthLabel("10m"), "10분");
    assert.equal(dailyLengthLabel(""), null);
    assert.equal(dailyLengthLabel("15m"), null);
  });
});
