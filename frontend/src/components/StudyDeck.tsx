"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { StudyCard } from "@/lib/study-plan";
import { project, rubber, spring } from "@/lib/spring";

/**
 * 일일공부의 공부 단계.
 *
 * 문제를 풀기 전에 오늘 나올 단어와 문장을 카드로 훑어본다. **채점하지
 * 않는다** - 좌우 어느 쪽으로 넘겨도 이동일 뿐이고, 맞고 틀리고는 이
 * 뒤의 문제풀이가 가린다. 그래서 되돌아갈 수 있다. 방금 본 것을 다시
 * 보는 건 공부하는 동안 당연한 동작인데, 채점하는 화면에서는 그게 곧
 * 답을 고치는 것이 되어 막혀 있다.
 *
 * 뜻을 처음부터 보여주지 않는 이유: 단어와 뜻이 같이 보이면 읽기가 되고,
 * 가려두면 떠올리기가 된다. 기억은 꺼낼 때 굳는다.
 *
 * **키캡 셋이 장식이 아니다.** 드래그로 할 수 있는 모든 것을 버튼으로도
 * 할 수 있어야 한다 - 키보드와 화면 낭독기에는 이쪽이 유일한 길이다.
 */
export function StudyDeck({
  cards,
  onDone,
}: {
  cards: StudyCard[];
  /** 마지막 장에서 문제풀이로 넘어갈 때. 되돌아오지 않는다. */
  onDone: () => void;
}) {
  const [index, setIndex] = useState(0);
  const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());

  // 맨 위 카드의 DOM. 드래그가 여기에 직접 transform 을 쓴다.
  const topRef = useRef<HTMLElement | null>(null);
  // 카드가 놓이는 상자. 제스처를 여기서 받는다 - 카드는 넘어갈 때
  // 사라지지만 이 상자는 안 사라진다.
  const stageRef = useRef<HTMLDivElement | null>(null);
  // 지금 도는 스프링을 끊는 함수. 손을 대면 즉시 끊어 그 자리에서 이어받는다.
  const stopRef = useRef<(() => void) | null>(null);
  // 드래그 중인 포인터. null 이면 안 끌고 있다.
  const dragRef = useRef<{
    id: number;
    originX: number;
    startY: number;
    startedAt: number;
    x: number;
    trail: { x: number; t: number }[];
    decided: "none" | "deck" | "scroll";
  } | null>(null);

  // 전역 CSS 의 prefers-reduced-motion 블록은 CSS 애니메이션만 0 으로
  // 만든다. 여기 움직임은 JS 가 transform 을 직접 쓰므로 그 블록이 안
  // 닿는다. 직접 본다.
  const reduced = useRef(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    reduced.current = query.matches;
    const sync = () => (reduced.current = query.matches);
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  // 화면을 떠날 때 도는 루프를 끊는다. 안 끊으면 사라진 DOM 에 계속 쓴다.
  useEffect(() => () => stopRef.current?.(), []);

  const total = cards.length;
  const atStart = index === 0;
  const atEnd = index >= total - 1;

  const setX = useCallback((value: number) => {
    const el = topRef.current;
    if (!el) return;
    // 살짝 기울인다. 평행이동만으로는 종이가 미끄러지는 것처럼 보이고,
    // 각도가 붙으면 손으로 집어 든 것처럼 읽힌다.
    el.style.transform = `translate3d(${value}px,0,0) rotate(${value * 0.035}deg)`;
  }, []);

  /**
   * 다음/이전 카드로. dir: +1 다음, -1 이전.
   *
   * **index 를 먼저 옮기고 그다음에 떠나는 카드를 애니메이션한다.**
   * 반대로 - 스프링이 끝나면 index 를 옮기는 식으로 - 두면 세 가지가
   * 한꺼번에 깨진다. 스프링의 중단은 onDone 을 안 부르기 때문이다.
   *
   *   연타하면  1차 스프링이 끊겨 그 land 가 사라지고, 두 번 눌러도
   *             한 장만 넘어간다
   *   날아가는  중간에 손을 대면 index 는 그대로인데 transform 만 화면
   *   카드를    밖에 멈춘다. 손을 떼면 넘겼던 카드가 되돌아온다
   *   잡으면
   *   언마운트  캡처를 쥔 카드가 사라져 pointercancel 이 안 와서
   *             드래그 상태가 안 풀린다
   *
   * 지금은 index 가 즉시 바뀌므로 위 셋 다 생기지 않는다. 떠나는 카드는
   * 이미 화면에서 빠진 뒤라, 그 자리를 채우는 것은 다음 카드의 등장이다.
   */
  const go = useCallback(
    (dir: 1 | -1) => {
      // 진행 중인 드래그가 있으면 버린다. 기준(originX)이 옛 카드의
      // transform 으로 잡힌 값이라, 카드가 바뀌면 그 기준을 새 카드가
      // 물려받아 화면 밖에서 시작한다.
      //
      // 핸들러가 안 사라지는 무대에 붙어 있어서 드래그가 index 변경을
      // 가로질러 살아남는다 - 카드에 붙어 있던 시절에는 언마운트가
      // 알아서 끊어줬다. 손가락을 쥔 채 키보드로 키캡을 누르면 닿는다.
      dragRef.current = null;
      setIndex((current) => {
        const next = current + dir;
        // 범위를 여기서 막는다. atStart/atEnd 로 막으면 그 값이 옛
        // 클로저에 잡혀 마지막 장 너머로 밀리고, 그러면 visible 이
        // 빈 배열이 되어 카드가 통째로 사라진다.
        if (next < 0 || next >= total) return current;
        return next;
      });
      // 새 맨 위 카드는 가운데에서 시작한다. 이전 카드가 남긴 값이
      // 그대로 있으면 다음 장이 화면 밖에서 나타난다.
      requestAnimationFrame(() => setX(0));
    },
    [total, setX],
  );

  const openTop = useCallback(() => {
    setOpened((prev) => {
      if (prev.has(index)) return prev;
      // Set 은 그 자리에서 고치면 참조가 같아서 다시 그리지 않는다.
      return new Set(prev).add(index);
    });
  }, [index]);

  /* ---- 제스처 ---- */

  const onPointerDown = (event: React.PointerEvent<HTMLElement>) => {
    // 이미 한 손가락이 끌고 있으면 두 번째는 무시한다. 안 그러면 나중
    // 손가락이 앞의 상태를 덮어써서, 앞 손가락을 뗄 때 id 가 안 맞아
    // 아무 정리도 안 되고 카드가 끌린 자리에 멈춘다.
    if (dragRef.current) return;

    // 날아가는 중이라도 잡으면 그 자리에서 멈춘다. 이게 없으면 손을
    // 댔는데 카드가 계속 도망간다.
    stopRef.current?.();
    stopRef.current = null;

    // 캡처는 이 상자가 쥔다. 카드가 아니라 - 카드는 넘어갈 때 사라진다.
    event.currentTarget.setPointerCapture(event.pointerId);

    // 위치는 카드에서 읽는다. 움직이는 것은 카드이기 때문이다.
    const card = topRef.current;
    const startX = card ? currentX(card) : 0;
    dragRef.current = {
      id: event.pointerId,
      originX: event.clientX - startX,
      startY: event.clientY,
      startedAt: event.timeStamp,
      x: startX,
      trail: [{ x: event.clientX, t: event.timeStamp }],
      decided: "none",
    };
  };

  const onPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== event.pointerId) return;

    const dx = event.clientX - drag.originX;
    const dy = event.clientY - drag.startY;

    // 가로인지 세로인지 한 번만 정하고 그 뒤로는 안 바꾼다. 매 프레임
    // 다시 재면 대각선으로 끌 때 덱과 스크롤 사이를 오간다.
    if (drag.decided === "none") {
      if (Math.abs(dx) > 8 || Math.abs(dy) > 8) {
        drag.decided = Math.abs(dx) > Math.abs(dy) ? "deck" : "scroll";
      }
    }
    if (drag.decided === "scroll") return;

    // 양 끝에서는 저항이 붙는다. 딱 멈추면 화면이 굳은 것으로 보이고,
    // 그대로 따라가면 더 있는 줄 안다.
    // 무대를 직접 잰다. currentTarget.parentElement 로 두면 안 된다 -
    // 핸들러가 카드에서 무대로 올라가면서 currentTarget 의 의미가
    // 바뀌었고, 그 표현은 이제 무대의 **부모**를 가리킨다. 지금은 둘의
    // 폭이 우연히 같아 증상이 없지만, 무대에 가로 여백이 붙는 날
    // 고무줄 저항만 조용히 어긋난다.
    const width = stageRef.current?.clientWidth ?? 320;
    const blocked = (atStart && dx > 0) || (atEnd && dx < 0);
    const next = blocked ? rubber(dx, width) : dx;

    drag.x = next;
    setX(next);
    drag.trail.push({ x: event.clientX, t: event.timeStamp });
    if (drag.trail.length > 6) drag.trail.shift();
  };

  const endDrag = (event: React.PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== event.pointerId) return;
    dragRef.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // 포인터가 이미 풀린 경우. 할 일이 없다.
    }

    // 거의 안 움직였고 짧게 눌렀으면 탭이다. click 을 따로 듣지 않는
    // 이유: 드래그가 끝날 때도 click 이 함께 나서 원치 않게 펼쳐진다.
    //
    // **세로로 정한 것은 탭이 아니다.** drag.x 는 가로만 담고, 세로로
    // 정해지면(155행) 그 뒤로 갱신을 멈춘다. 그래서 화면을 빠르게 쓸어
    // 내리기만 해도 "가로로 안 움직였고 250ms 안" 이 성립해서 뜻이
    // 펼쳐진다. 폰에서 그냥 스크롤할 때마다 일어난다.
    const moved = Math.abs(drag.x) > 6;
    if (drag.decided !== "scroll" && !moved && event.timeStamp - drag.startedAt < 250) {
      openTop();
      return;
    }
    if (drag.decided !== "deck") {
      setX(0);
      return;
    }

    const first = drag.trail[0];
    const last = drag.trail[drag.trail.length - 1];
    const span = Math.max(1, last.t - first.t);
    const velocity = ((last.x - first.x) / span) * 1000;

    // 놓은 자리가 아니라 가려던 자리로 판정한다. 이게 없으면 짧고 빠르게
    // 튕긴 손짓이 "조금밖에 안 갔다" 로 읽혀 제자리로 돌아온다.
    const landing = drag.x + project(velocity);
    if (Math.abs(landing) > 105) {
      const dir: 1 | -1 = landing < 0 ? 1 : -1;
      if ((dir > 0 && !atEnd) || (dir < 0 && !atStart)) {
        go(dir);
        return;
      }
    }

    const el = topRef.current;
    if (!el || reduced.current) {
      setX(0);
      return;
    }
    // 안 넘어가면 제자리로. 손가락이 만든 속도를 이어받되 안 튕긴다.
    stopRef.current?.();
    stopRef.current = spring(drag.x, 0, velocity, 1, 0.34, setX, () => {
      stopRef.current = null;
    });
  };

  if (total === 0) return null;

  // 뒤 두 장까지만 그린다. 그 너머는 어차피 안 보이는데 DOM 만 늘어난다.
  const visible = cards
    .map((card, at) => ({ card, at, depth: at - index }))
    .filter(({ depth }) => depth >= 0 && depth <= 2)
    .reverse();

  const isOpen = opened.has(index);
  const rest = total - index - 1;

  return (
    <div className="flex flex-1 flex-col">
      {/* 어디까지 왔는지. 문제풀이가 이 뒤에 있다는 것을 계속 알린다 -
          끝이 안 보이면 훑기가 숙제로 바뀐다. */}
      <div className="flex items-center gap-2.5">
        <span className="shrink-0 font-mono text-[11px] font-semibold text-slate-400">
          공부
        </span>
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={index + 1}
          aria-label="공부 진행"
          className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10"
        >
          <div
            className="h-full rounded-full bg-focus transition-[width] duration-300 ease-out"
            style={{ width: `${((index + 1) / total) * 100}%` }}
          />
        </div>
        <span className="shrink-0 font-mono text-[11px] text-slate-400 tabular-nums">
          {rest === 0 ? "마지막" : `${rest}장 남음`}
        </span>
      </div>

      {/* touch-action 이 없으면 iOS 가 가로 드래그를 뒤로가기로 먼저
          가져간다. 데스크톱에서는 멀쩡하고 폰에서만 안 되는 종류다.

          아래 여백은 뒤 카드가 내려가 앉는 자리다(depth 당 11px, 최대
          두 장이라 22px). 없으면 세 번째 카드가 키캡에 닿는다. */}
      {/* **제스처를 카드가 아니라 이 상자가 받는다.** 카드에 걸면
          setPointerCapture 를 쥔 노드가 다음 장으로 넘어갈 때 언마운트되고,
          그러면 브라우저가 캡처를 암묵 해제하면서 보내는 pointercancel 이
          사라진 노드로 가서 드래그 상태가 안 풀린다. 이 상자는 덱이
          살아 있는 동안 안 사라진다. */}
      <div
        ref={stageRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className="relative mt-4 mb-6 flex-1 touch-pan-y"
      >
        {visible.map(({ card, at, depth }) => (
          <StudyCardView
            key={card.id}
            card={card}
            depth={depth}
            opened={opened.has(at)}
            order={at + 1}
            total={total}
            ref={depth === 0 ? topRef : undefined}
          />
        ))}
      </div>

      <div className="mt-4 flex gap-2">
        <DeckKey onClick={() => go(-1)} disabled={atStart} cap="이전">
          ←
        </DeckKey>
        <DeckKey onClick={openTop} disabled={isOpen} cap="뜻 보기" wide>
          {isOpen ? "펼침" : "뜻"}
        </DeckKey>
        {atEnd ? (
          <DeckKey onClick={onDone} cap="시작" primary>
            문제풀이 →
          </DeckKey>
        ) : (
          <DeckKey onClick={() => go(1)} cap="다음" primary>
            다음 →
          </DeckKey>
        )}
      </div>
    </div>
  );
}

/** 지금 화면에 그려진 가로 위치. 스프링이 여기서 이어받는다. */
function currentX(el: HTMLElement): number {
  const value = new DOMMatrixReadOnly(getComputedStyle(el).transform).m41;
  return Number.isFinite(value) ? value : 0;
}

/** 눌리는 키캡. 드래그로 되는 것은 전부 이걸로도 돼야 한다. */
function DeckKey({
  children,
  cap,
  onClick,
  disabled,
  primary,
  wide,
}: {
  children: React.ReactNode;
  cap: string;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
  wide?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={[
        "flex min-h-12 flex-col items-center justify-center gap-px rounded-2xl border font-semibold",
        "transition-[scale,border-color] duration-[120ms] ease-press active:scale-[0.96]",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
        "disabled:opacity-40",
        wide ? "flex-[0_0_26%]" : "flex-1",
        primary
          ? "border-focus bg-focus text-focus-on"
          : "border-white/25 text-slate-100 hover:border-white/45",
      ].join(" ")}
    >
      <span className="text-sm">{children}</span>
      <span className="font-mono text-[9px] font-medium opacity-60">{cap}</span>
    </button>
  );
}

/** 카드 한 장. 뜻은 접혀 있고 탭하면 펼쳐진다. */
function StudyCardView({
  card,
  depth,
  opened,
  order,
  total,
  ref,
  ...handlers
}: {
  card: StudyCard;
  depth: number;
  opened: boolean;
  order: number;
  total: number;
  ref?: React.Ref<HTMLElement>;
} & Pick<
  React.HTMLAttributes<HTMLElement>,
  "onPointerDown" | "onPointerMove" | "onPointerUp" | "onPointerCancel"
>) {
  const isSentence = card.kind === "sentence";

  return (
    <article
      ref={ref}
      {...handlers}
      // 뒤 카드는 조금 작고 아래로 내려가 있다. 겹쳐진 두께가 보이면
      // 앞으로 몇 장이 더 있다는 것이 숫자를 안 읽어도 전달된다.
      style={{
        transform: `translate3d(0,${depth * 11}px,0) scale(${1 - depth * 0.045})`,
        zIndex: 10 - depth,
      }}
      className={[
        // inset-0 으로 남은 높이를 채운다. top-0 만 주면 카드가 내용
        // 높이로 줄어들어, 뒤 카드가 앞 카드 아래로 삐져나온다.
        //
        // select-none: 끄는 동안 글자가 파랗게 잡힌다. 드래그로 넘기는
        // 화면이라 선택은 쓸 일이 없고, 잡히면 다음 드래그도 방해한다.
        "absolute inset-0 flex flex-col overflow-hidden rounded-2xl select-none",
        "border border-white/12 bg-slate-950/55 backdrop-blur-sm",
        depth === 0 ? "cursor-grab touch-pan-y active:cursor-grabbing" : "",
      ].join(" ")}
      aria-hidden={depth > 0}
    >
      <header className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5">
        <span className="font-mono text-[10px] text-slate-400 tabular-nums">
          {order} / {total}
        </span>
        {card.label && (
          <span className="ml-auto rounded-md border border-focus/35 bg-focus/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wider text-focus">
            {card.label}
          </span>
        )}
      </header>

      <div className="flex flex-1 flex-col px-4 py-4">
        {/* 문장은 길어서 작게 둔다. 단어와 같은 크기로 두면 두 줄이 넘어
            카드 밖으로 밀린다. */}
        <p
          lang="en"
          className={
            isSentence
              ? "font-mono text-base leading-snug font-bold tracking-tight text-white"
              : "font-mono text-[2rem] leading-none font-extrabold tracking-tighter text-white"
          }
        >
          {card.term}
        </p>

        {card.reading && (
          <p
            lang="en-US"
            className="mt-2.5 font-mono text-[11px] text-slate-400"
          >
            {card.reading}
          </p>
        )}

        {/* 뜻은 카드 가운데쯤에 온다. 위에 붙여두면 단어와 붙어 읽혀서
            "가려져 있다가 나온 것" 이라는 느낌이 사라진다. */}
        <div className="mt-6 flex flex-1 flex-col justify-start">
          {opened ? (
            <div className="rise">
              <p className="text-base leading-snug font-bold tracking-tight text-slate-50">
                {card.meaning}
              </p>
              {card.note && (
                <p className="mt-2.5 rounded-r-lg border-l-2 border-focus/60 bg-slate-950/50 py-2 pr-2.5 pl-2.5 font-mono text-[10px] leading-relaxed text-slate-400">
                  {card.note}
                </p>
              )}
            </div>
          ) : (
            // 에디터가 코드를 접었을 때 쓰는 표현을 그대로 쓴다. 설명하는
            // 문구보다 개발자가 매일 보는 모양이 알아보기 쉽다.
            <div className="flex items-center gap-2 rounded-xl border-2 border-dashed border-white/12 bg-slate-950/40 px-3 py-2.5">
              <span aria-hidden className="font-mono text-xs text-focus">
                ▸
              </span>
              <span className="font-mono text-[10px] text-slate-400">
                {card.note ? "2 lines hidden" : "1 line hidden"}
              </span>
              <span className="sr-only">탭하면 뜻이 펼쳐집니다</span>
              <span aria-hidden className="ml-auto flex gap-1">
                <i className="block h-1.5 w-6 rounded-sm bg-white/10" />
                <i className="block h-1.5 w-4 rounded-sm bg-white/10" />
              </span>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
