/**
 * 시작 화면 로고 그림과 그 폭 상한이 서로 맞는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * page.tsx 는 로고 높이가 화면 높이의 30% 를 넘지 않게 폭을
 * `calc(30svh*가로/세로)` 로 묶는다. 이 가로세로는 그림 파일에서 손으로 옮겨
 * 적은 값이라, logo.webp 만 다른 비율로 바꾸면 상한이 조용히 틀어진다.
 * 세로가 짧은 폰(375x667, 폴드 접은 416x657)에서 아래 버튼이 화면 밖으로
 * 밀리는 것은 눈으로 봐야만 드러나므로 여기서 숫자로 막는다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

/** WebP 의 가로세로. 손실(VP8), 무손실(VP8L), 확장(VP8X) 셋을 읽는다. */
function webpSize(path: string): { width: number; height: number } {
  const data = readFileSync(path);
  assert.equal(data.toString("latin1", 0, 4), "RIFF", "RIFF 가 아니다");
  assert.equal(data.toString("latin1", 8, 12), "WEBP", "WebP 가 아니다");
  const chunk = data.toString("latin1", 12, 16);
  if (chunk === "VP8 ") {
    return { width: data.readUInt16LE(26) & 0x3fff, height: data.readUInt16LE(28) & 0x3fff };
  }
  if (chunk === "VP8L") {
    const bits = data.readUInt32LE(21);
    return { width: (bits & 0x3fff) + 1, height: ((bits >> 14) & 0x3fff) + 1 };
  }
  if (chunk === "VP8X") {
    return { width: data.readUIntLE(24, 3) + 1, height: data.readUIntLE(27, 3) + 1 };
  }
  assert.fail(`모르는 WebP 형식: ${chunk}`);
}

describe("시작 화면 로고", () => {
  const { width, height } = webpSize(join(HERE, "logo.webp"));
  const page = readFileSync(join(HERE, "page.tsx"), "utf8");

  it("폭 상한의 가로세로 비가 그림 파일과 같다", () => {
    const ratio = page.match(/calc\(30svh\*(\d+)\/(\d+)\)/);
    assert.ok(ratio, "로고 폭 상한 calc(30svh*가로/세로) 를 못 찾았다");
    // 숫자 자체가 아니라 비를 본다. 같은 그림을 2배로 다시 뽑아도 통과해야 한다.
    const [a, b] = [Number(ratio[1]), Number(ratio[2])];
    assert.equal(a * height, b * width, `상한 ${a}/${b}, 그림 ${width}x${height}`);
  });

  it("그림은 원본 아이콘에서 줄이지 않고 잘라 낸 해상도다", () => {
    // 원본 아이콘(1254px)에서 dv 마크의 폭이 745px 라 그보다 큰 그림은 없다.
    // 그래서 넓게 그려지는 폰(폭 342px, 배율 3)에서는 1.3배쯤 늘어난다.
    // 이 하한은 작게 줄여 저장해 더 흐려지는 것만 막는다.
    assert.ok(width >= 745, `가로 ${width}px`);
  });
});
