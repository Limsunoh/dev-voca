"use client";

import { useEffect, useId, useRef, useState } from "react";

/**
 * 큰 사진에서 쓸 부분을 오려 내는 창. 4MB 가 넘는 사진을 고르면 내정보가 띄운다.
 *
 * 큰 사진은 그대로 못 올린다. 화면 서버(Vercel)가 받는 요청이 4.5MB 까지라서다
 * (ProfileForm 의 PHOTO_MAX_BYTES). 예전에는 "4MB 까지" 로 거절했는데, 폰 카메라
 * 원본은 그보다 큰 경우가 많아 사용자가 직접 줄여 와야 했다. 여기서 틀 안에 들어갈
 * 부분을 고르게 하고, 그 부분만 512px JPEG 로 그려 보낸다. 서버는 어차피 256px 로 줄여
 * 저장한다(accounts.AVATAR_PHOTO_SIZE). JPEG 라 투명한 부분은 흰색이 된다.
 *
 * 틀의 모서리는 아바타와 같은 38% 다(Avatar 의 cornerFor). 고른 모양이 그대로 보인다.
 *
 * 라이브러리를 넣지 않는다. 끌기·두 손가락 확대는 pointer 이벤트로, 그리기는 canvas 로
 * 된다(.claude/skills/devvoca-design 의 의존성 기준).
 *
 * 위치는 "틀 가운데에 오는 사진의 점" 을 원본 픽셀로 들고(cx, cy), 화면에는 틀에 대한
 * 비율(%)로 그린다. 틀 크기가 바뀌어도(폰을 돌림) 고른 부분이 그대로다. 계산은 아래 세
 * 함수(clampView, panView, zoomView)에 있고 PhotoCropper.test.mts 가 본다.
 */

/** 보낼 사진의 한 변(px). 서버 저장 크기(256)의 두 배라 줄여도 흐려지지 않는다. */
const OUTPUT_SIZE = 512;
/** 사진의 짧은 변이 틀에 꼭 맞는 크기에서 몇 배까지 키우나. */
export const MAX_ZOOM = 4;
/** 화살표 키 한 번에 옮기는 거리(화면 px). */
const KEY_STEP = 12;
// 이보다 큰 사진은 열지 않는다. 화면에 그리려고 압축을 풀면 픽셀마다 4바이트라 1억 픽셀이 400MB 다. 폰 카메라의
// 고화소 모드(2억 픽셀)를 열다가 탭이 죽는 것보다 안내가 낫다.
// ponytail: 기기 메모리를 모르고 정한 값이다. 실제로 죽는 기기가 나오면 낮춘다.
const MAX_PIXELS = 100_000_000;

const CANNOT_OPEN = "이 사진은 열 수 없습니다. 다른 사진을 골라주세요.";
const TOO_BIG = "사진이 너무 커서 열 수 없습니다. 다른 사진을 골라주세요.";

export type Size = { w: number; h: number };
export type View = { zoom: number; cx: number; cy: number };

/** 틀 밖으로 사진 가장자리가 들어오지 않게 크기와 가운데 점을 묶는다. */
export function clampView(view: View, size: Size): View {
  const zoom = Math.min(MAX_ZOOM, Math.max(1, view.zoom));
  // 틀 한 변이 원본 픽셀로 몇인가. 그 절반만큼은 가장자리에서 떨어져 있어야 한다.
  const half = Math.min(size.w, size.h) / zoom / 2;
  return {
    zoom,
    cx: Math.min(size.w - half, Math.max(half, view.cx)),
    cy: Math.min(size.h - half, Math.max(half, view.cy)),
  };
}

/** 화면 1px 이 원본 몇 px 인가. 틀 한 변(frame px)이 원본으로 (짧은 변 / zoom) 이다. */
function sourcePerPixel(zoom: number, size: Size, frame: number): number {
  return Math.min(size.w, size.h) / zoom / frame;
}

/** 손가락을 (dx, dy) 화면 px 만큼 끌었다. 사진이 손가락을 따라간다. */
export function panView(view: View, size: Size, dx: number, dy: number, frame: number): View {
  const scale = sourcePerPixel(view.zoom, size, frame);
  return clampView({ ...view, cx: view.cx - dx * scale, cy: view.cy - dy * scale }, size);
}

/**
 * 틀 가운데에서 (ax, ay) 화면 px 떨어진 점을 붙잡은 채 크기를 zoom 으로 바꾼다.
 * 붙잡은 점 아래의 원본 점이 바꾼 뒤에도 같은 화면 자리에 남는다.
 */
export function zoomView(
  view: View,
  size: Size,
  zoom: number,
  ax: number,
  ay: number,
  frame: number,
): View {
  const next = Math.min(MAX_ZOOM, Math.max(1, zoom));
  // 키우면 화면 1px 이 덮는 원본이 줄어든다. 그 차이만큼 가운데 점을 붙잡은 점 쪽으로
  // 당겨야 붙잡은 점이 손가락 아래에 남는다.
  const scaleChange = sourcePerPixel(view.zoom, size, frame) - sourcePerPixel(next, size, frame);
  return clampView(
    { zoom: next, cx: view.cx + ax * scaleChange, cy: view.cy + ay * scaleChange },
    size,
  );
}

export function PhotoCropper({
  file,
  onClose,
  onDone,
}: {
  file: File;
  /** 올리지 않고 닫았을 때. 사진을 못 열었으면 그 안내를 넘긴다. */
  onClose: (error?: string) => void;
  /** 오려 낸 사진(JPEG 512px). */
  onDone: (photo: File) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const titleId = useId();
  const hintId = useId();

  // 읽어 들인 사진의 주소와 원본 크기. 다 읽기 전에는 없다.
  const [source, setSource] = useState<{ url: string } & Size>();
  const [view, setView] = useState<View>({ zoom: 1, cx: 0, cy: 0 });
  // 올리기를 눌러 사진을 만드는 중. 큰 사진은 그리는 데 1초 가까이 걸린다.
  const [busy, setBusy] = useState(false);
  // 창이 한 번 끝났다(올림·닫음·못 엶). 그 뒤에 오는 것은 무시한다. 올리기를 누르고
  // 사진을 만드는 동안 취소를 누르면, 만든 사진이 뒤늦게 올라가면 안 된다.
  const finished = useRef(false);

  // 손가락마다 마지막 위치. 둘이면 두 손가락 확대다.
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{ distance: number; zoom: number } | null>(null);

  function finish(after: () => void) {
    if (finished.current) return;
    finished.current = true;
    dialogRef.current?.close();
    after();
  }

  // 사진을 다 읽은 뒤에 크기를 알고 처음 위치(가운데, 짧은 변이 틀에 꼭 맞게)를 정한다.
  // 주소는 여기서 만들고 여기서 거둔다. 개발 모드는 효과를 두 번 돌리는데(StrictMode),
  // 다른 곳에서 만든 주소를 여기서 거두면 두 번째에는 거둔 주소를 그린다.
  useEffect(() => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    // 브라우저가 못 여는 형식(안드로이드 Chrome 의 HEIC 등)이면 onerror 가 온다.
    image.onerror = () => finish(() => onClose(CANNOT_OPEN));
    image.onload = () => {
      const { naturalWidth: w, naturalHeight: h } = image;
      if (!w || !h) return finish(() => onClose(CANNOT_OPEN));
      if (w * h > MAX_PIXELS) return finish(() => onClose(TOO_BIG));
      setSource({ url, w, h });
      setView({ zoom: 1, cx: w / 2, cy: h / 2 });
    };
    image.src = url;
    return () => {
      image.onload = null;
      image.onerror = null;
      URL.revokeObjectURL(url);
    };
    // onClose 는 부모가 그릴 때마다 새로 만드는 함수다. 넣으면 부모가 다시 그릴 때마다
    // 사진을 다시 읽는다. 사진이 바뀔 때만 다시 읽는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  // showModal() 이라야 포커스 가둠·Esc·뒤 막기가 붙는다(LeaveConfirm 주석).
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  function frameWidth(): number {
    return frameRef.current?.getBoundingClientRect().width || 1;
  }

  function pan(dx: number, dy: number) {
    if (!source) return;
    const frame = frameWidth();
    setView((current) => panView(current, source, dx, dy, frame));
  }

  /** 틀 안의 한 점(화면 px, 틀 왼쪽 위 기준)을 붙잡고 크기를 바꾼다. 없으면 가운데. */
  function zoomTo(zoom: number, anchor?: { x: number; y: number }) {
    if (!source) return;
    const frame = frameWidth();
    const ax = anchor ? anchor.x - frame / 2 : 0;
    const ay = anchor ? anchor.y - frame / 2 : 0;
    setView((current) => zoomView(current, source, zoom, ax, ay, frame));
  }

  /** 손가락이 정확히 둘일 때 두 손가락 확대의 기준을 다시 잡는다. 셋에서 하나를 떼도 튀지 않게. */
  function resetPinch() {
    if (pointers.current.size !== 2) {
      pinch.current = null;
      return;
    }
    const [a, b] = [...pointers.current.values()];
    const distance = Math.hypot(a.x - b.x, a.y - b.y);
    pinch.current = distance > 0 ? { distance, zoom: view.zoom } : null;
  }

  function release(pointerId: number) {
    pointers.current.delete(pointerId);
    resetPinch();
  }

  function crop() {
    const image = imageRef.current;
    if (!image || !source || busy || finished.current) return;
    setBusy(true);
    const canvas = document.createElement("canvas");
    canvas.width = OUTPUT_SIZE;
    canvas.height = OUTPUT_SIZE;
    const context = canvas.getContext("2d");
    if (!context) {
      finish(() => onClose(CANNOT_OPEN));
      return;
    }
    // JPEG 는 투명을 못 담는다. 투명한 PNG 가 검게 나오지 않게 흰 바탕을 먼저 깐다.
    context.fillStyle = "#fff";
    context.fillRect(0, 0, OUTPUT_SIZE, OUTPUT_SIZE);
    context.imageSmoothingQuality = "high";
    const side = Math.min(source.w, source.h) / view.zoom;
    context.drawImage(
      image,
      view.cx - side / 2,
      view.cy - side / 2,
      side,
      side,
      0,
      0,
      OUTPUT_SIZE,
      OUTPUT_SIZE,
    );
    canvas.toBlob(
      (blob) => {
        if (!blob) finish(() => onClose(CANNOT_OPEN));
        else finish(() => onDone(new File([blob], "photo.jpg", { type: "image/jpeg" })));
      },
      "image/jpeg",
      0.9,
    );
  }

  const short = source ? Math.min(source.w, source.h) : 1;

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={hintId}
      // Esc 나 안드로이드 뒤로 가기로 닫으면 cancel 이 온다. 브라우저가 닫게 두지 않고
      // finish 로 닫아야 부모가 고른 사진을 비운다.
      onCancel={(event) => {
        event.preventDefault();
        finish(() => onClose());
      }}
      // 폭과 여백, 바탕은 LeaveConfirm 과 같다(이유도 거기). 틀이 정사각형이라 폭만 정하면
      // 높이가 따라온다.
      className="pop m-auto w-[min(22rem,calc(100vw-2rem))] p-[clamp(1rem,7vw,1.5rem)] backdrop:bg-[rgb(25_21_18/0.72)]"
      style={{
        background: "var(--paper)",
        color: "var(--foreground)",
        borderRadius: "var(--radius-sheet)",
        border: 0,
        boxShadow: "var(--lift-sheet)",
      }}
    >
      <h2
        id={titleId}
        style={{
          fontSize: "var(--text-lg)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
        }}
      >
        쓸 부분 고르기
      </h2>
      <p
        id={hintId}
        className="mt-2 text-sm"
        style={{ lineHeight: "var(--leading-relaxed)", color: "var(--text-muted)" }}
      >
        사진이 4MB 보다 커서 틀 안에 들어온 부분만 올립니다. 끌어서 옮기고, 막대나 두
        손가락으로 크기를 바꾸세요.
      </p>

      <div
        ref={frameRef}
        tabIndex={0}
        role="group"
        aria-label="사진 위치. 화살표 키로 옮깁니다."
        // touch-none 이 없으면 끄는 동안 화면이 같이 스크롤되거나 브라우저가 확대한다.
        className="relative mt-4 aspect-square w-full cursor-grab touch-none select-none overflow-hidden focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:cursor-grabbing"
        style={{ borderRadius: "38%", background: "var(--surface-field)" }}
        onPointerDown={(event) => {
          // 만드는 중에는 옮기지 않는다. 올라가는 것은 누른 순간의 부분이다.
          if (busy) return;
          // 마우스 오른쪽 단추는 메뉴가 떠서 pointerup 이 안 온다. 그러면 끌기가 안 끝난다.
          if (event.pointerType === "mouse" && event.button !== 0) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
          resetPinch();
        }}
        onPointerMove={(event) => {
          const last = pointers.current.get(event.pointerId);
          // 올리기 전부터 누르고 있던 손가락도 만드는 중에는 옮기지 않는다.
          if (!last || busy) return;
          pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
          if (pointers.current.size === 1) {
            pan(event.clientX - last.x, event.clientY - last.y);
            return;
          }
          if (pointers.current.size === 2 && pinch.current) {
            const [a, b] = [...pointers.current.values()];
            const rect = event.currentTarget.getBoundingClientRect();
            const distance = Math.hypot(a.x - b.x, a.y - b.y);
            zoomTo((pinch.current.zoom * distance) / pinch.current.distance, {
              x: (a.x + b.x) / 2 - rect.left,
              y: (a.y + b.y) / 2 - rect.top,
            });
          }
        }}
        onPointerUp={(event) => release(event.pointerId)}
        onPointerCancel={(event) => release(event.pointerId)}
        onKeyDown={(event) => {
          // 끌기와 같은 방향이다. 오른쪽 화살표면 사진이 오른쪽으로 간다.
          const moves: Record<string, [number, number]> = {
            ArrowLeft: [-KEY_STEP, 0],
            ArrowRight: [KEY_STEP, 0],
            ArrowUp: [0, -KEY_STEP],
            ArrowDown: [0, KEY_STEP],
          };
          const move = moves[event.key];
          if (!move || busy) return;
          event.preventDefault();
          pan(...move);
        }}
      >
        {source && (
          // 원본을 그대로 보여 준다. next/image 는 이 object URL 을 다루지 못하고 줄일 이유도 없다.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            ref={imageRef}
            src={source.url}
            alt=""
            draggable={false}
            className="pointer-events-none absolute max-w-none"
            style={{
              width: `${((source.w * view.zoom) / short) * 100}%`,
              height: `${((source.h * view.zoom) / short) * 100}%`,
              left: `${(0.5 - (view.cx * view.zoom) / short) * 100}%`,
              top: `${(0.5 - (view.cy * view.zoom) / short) * 100}%`,
            }}
          />
        )}
      </div>

      <label className="mt-4 flex items-center gap-3 text-sm" style={{ color: "var(--text-muted)" }}>
        <span className="shrink-0" style={{ fontWeight: "var(--weight-bold)" }}>
          크기
        </span>
        <input
          type="range"
          min={1}
          max={MAX_ZOOM}
          step={0.01}
          value={view.zoom}
          disabled={!source || busy}
          aria-valuetext={`${Math.round(view.zoom * 100)}%`}
          onChange={(event) => zoomTo(Number(event.currentTarget.value))}
          className="w-full min-w-0 rounded-[var(--radius-pill)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={{ minHeight: "var(--hit-min)", accentColor: "var(--brand)" }}
        />
      </label>

      {/* 버튼 줄은 LeaveConfirm 처럼 좁으면 위아래로 쌓인다. 여기서는 올리는 쪽이 갈색이다.
          되돌리기 어려운 동작이 아니고, 고르러 들어온 사람이 누를 쪽이다. */}
      <div className="mt-6 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => finish(() => onClose())}
          className="dv-btn flex flex-[1_1_7rem] items-center justify-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--paper)",
              color: "var(--text-muted)",
              border: 0,
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button-paper)",
            } as React.CSSProperties
          }
        >
          취소
        </button>
        <button
          type="button"
          disabled={!source || busy}
          onClick={crop}
          className="dv-btn flex flex-[1_1_7rem] items-center justify-center px-4 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--brand)",
              color: "var(--text-on-color)",
              border: 0,
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-black)",
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
        >
          {/* 좁은 폰(360px)에서 한 줄에 들게 짧게 둔다. 무엇을 올리는지는 제목이 말한다. */}
          {busy ? "만드는 중" : "올리기"}
        </button>
      </div>
    </dialog>
  );
}
