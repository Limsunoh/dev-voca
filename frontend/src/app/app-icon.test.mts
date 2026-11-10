/**
 * 앱 아이콘 검증.
 *
 * 실행: cd frontend && npm test
 *
 * Next 는 app 폴더의 icon.* / apple-icon.* 을 보고 <head> 에 링크를 단다.
 *
 *     icon.png        브라우저 탭. 둥근 사각형 밖이 투명해야 탭 위에 흰 모서리가
 *                     안 남는다
 *     apple-icon.png  폰 홈 화면. iOS 는 투명한 곳을 검게 칠하므로 불투명이어야 한다
 *     옛 아이콘       임시 icon.svg 나 favicon.ico 가 남으면 Next 가 링크를 여러 개
 *                     달고, 브라우저가 그쪽을 골라 옛 그림이 뜬다
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { inflateSync } from "node:zlib";

const HERE = dirname(fileURLToPath(import.meta.url));

const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
// 색 형식별 픽셀 하나의 바이트 수. 2 = RGB, 3 = 팔레트 번호, 6 = RGBA.
const CHANNELS: Record<number, number> = { 2: 3, 3: 1, 6: 4 };

type Png = { width: number; height: number; bytes: number; alpha: (x: number, y: number) => number };

/**
 * PNG 를 끝까지 풀어 픽셀의 불투명도를 돌려준다. 노드에 이미지 해석기가 없어 직접 푼다.
 * 8비트, 인터레이스 없음, 색 형식 2·3·6 만 다룬다. 그 밖은 조용히 넘기지 않고 실패한다.
 */
function readPng(name: string): Png {
  const data = readFileSync(join(HERE, name));
  assert.ok(data.subarray(0, 8).equals(SIGNATURE), `${name} 이 PNG 가 아니다`);

  const chunks: Record<string, Buffer[]> = {};
  for (let at = 8; at < data.length; ) {
    const length = data.readUInt32BE(at);
    const type = data.toString("latin1", at + 4, at + 8);
    (chunks[type] ??= []).push(data.subarray(at + 8, at + 8 + length));
    at += 12 + length;
  }

  const header = chunks.IHDR?.[0];
  assert.ok(header, `${name} 에 IHDR 이 없다`);
  const [width, height] = [header.readUInt32BE(0), header.readUInt32BE(4)];
  const [bitDepth, colorType, interlace] = [header[8], header[9], header[12]];
  const channels = CHANNELS[colorType];
  const transparency = chunks.tRNS?.[0];
  assert.ok(
    bitDepth === 8 && interlace === 0 && channels && !(colorType === 2 && transparency),
    `${name}: 다루지 않는 형식(비트 ${bitDepth}, 색 형식 ${colorType}, 인터레이스 ${interlace})`,
  );

  // 줄마다 맨 앞 1바이트가 필터 종류다. 필터는 왼쪽·위·왼쪽 위 픽셀로 값을 예측해
  // 차이만 적어 둔 것이라, 위에서부터 차례로 되돌린다.
  const raw = inflateSync(Buffer.concat(chunks.IDAT ?? []));
  const stride = width * channels;
  // 길이가 모자라거나 필터 번호가 틀리면 계산이 NaN 이 되고, & 0xff 가 그것을 0(투명)으로
  // 바꿔 "모서리가 투명하다" 를 통과시킨다. 그 전에 멈춘다.
  assert.equal(raw.length, height * (stride + 1), `${name}: 픽셀 데이터 길이가 안 맞는다`);
  const pixels = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    assert.ok(filter <= 4, `${name}: 모르는 필터 ${filter}`);
    for (let i = 0; i < stride; i++) {
      const left = i >= channels ? pixels[y * stride + i - channels] : 0;
      const up = y > 0 ? pixels[(y - 1) * stride + i] : 0;
      const upLeft = y > 0 && i >= channels ? pixels[(y - 1) * stride + i - channels] : 0;
      const p = left + up - upLeft;
      const [pa, pb, pc] = [Math.abs(p - left), Math.abs(p - up), Math.abs(p - upLeft)];
      const paeth = pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft;
      const predictor = [0, left, up, (left + up) >> 1, paeth][filter];
      pixels[y * stride + i] = (raw[y * (stride + 1) + 1 + i] + predictor) & 0xff;
    }
  }

  const alpha = (x: number, y: number) => {
    const at = y * stride + x * channels;
    if (colorType === 6) return pixels[at + 3];
    if (colorType === 2) return 255;
    return transparency?.[pixels[at]] ?? 255; // 팔레트. tRNS 에 없는 번호는 불투명
  };
  return { width, height, bytes: data.length, alpha };
}

const cornerAlphas = ({ width, height, alpha }: Png) =>
  [
    [0, 0],
    [width - 1, 0],
    [0, height - 1],
    [width - 1, height - 1],
  ].map(([x, y]) => alpha(x, y));

describe("앱 아이콘", () => {
  it("아이콘 파일은 icon.png 와 apple-icon.png 둘뿐이다", () => {
    const icons = readdirSync(HERE).filter((name) => /^(favicon|icon\d*|apple-icon\d*)\./.test(name));
    assert.deepEqual(icons.sort(), ["apple-icon.png", "icon.png"]);
  });

  it("탭 아이콘은 192px 이상 정사각형이다", () => {
    const icon = readPng("icon.png");
    assert.equal(icon.width, icon.height);
    assert.ok(icon.width >= 192, `너무 작다: ${icon.width}px`);
  });

  it("탭 아이콘은 네 모서리가 모두 투명하다", () => {
    assert.deepEqual(cornerAlphas(readPng("icon.png")), [0, 0, 0, 0]);
  });

  // 원본 로고에 잔 얼룩이 있어 색을 줄이지 않고 저장하면 220KB 가 된다.
  // 첫 방문마다 받는 파일이다.
  it("탭 아이콘은 50KB 를 넘지 않는다", () => {
    const { bytes } = readPng("icon.png");
    assert.ok(bytes <= 50_000, `${bytes} 바이트`);
  });

  it("홈 화면 아이콘은 iOS 기준 180px 정사각형이고 네 모서리까지 불투명하다", () => {
    const icon = readPng("apple-icon.png");
    assert.equal(icon.width, 180);
    assert.equal(icon.height, 180);
    assert.deepEqual(cornerAlphas(icon), [255, 255, 255, 255]);
  });
});
