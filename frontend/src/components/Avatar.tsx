/**
 * 프로필 그림.
 *
 * 서버가 "무엇을 그릴지" 를 정해서 내려준다(avatar_display). 프론트가
 * "구글 사진이 있으면 그것, 없으면 아바타" 규칙을 따로 들고 있으면 두 곳이
 * 어긋나고, 그러면 화면마다 다른 그림이 뜬다.
 *
 * 아바타는 파일이 아니라 SVG 다. 이미지 파일을 서버에 두면 배포할 때마다
 * 컨테이너 디스크가 초기화돼 사라지고, 외부 CDN 은 우리 화면이 남의 서버에
 * 의존하게 된다.
 */

"use client";

import { useState } from "react";

/** 서버가 내려주는 모양. backend 의 User.avatar_display 와 짝. */
export type AvatarDisplay =
  | { type: "photo"; url: string }
  | { type: "preset"; key: string };

export const AVATAR_KEYS = ["a1", "a2", "a3", "a4", "a5", "a6"] as const;

/**
 * 아바타 여섯 종.
 *
 * 색만 다른 게 아니라 모양도 다르게 둔다. 색만 다르면 색을 구분하기
 * 어려운 사람에게는 전부 같은 그림이다.
 */
const PRESETS: Record<
  string,
  { bg: string; fg: string; label: string; path: string }
> = {
  a1: {
    bg: "#1e293b",
    fg: "#e2e8f0",
    label: "터미널",
    path: "M14 18l8 8-8 8M28 34h12",
  },
  a2: {
    bg: "#0f766e",
    fg: "#ccfbf1",
    label: "중괄호",
    path: "M22 14c-4 0-4 4-4 6s0 6-4 6c4 0 4 4 4 6s0 6 4 6M42 14c4 0 4 4 4 6s0 6 4 6c-4 0-4 4-4 6s0 6-4 6",
  },
  a3: {
    bg: "#7c2d12",
    fg: "#fed7aa",
    label: "책",
    path: "M16 16h14v32H16zM34 16h14v32H34zM32 16v32",
  },
  a4: {
    bg: "#4c1d95",
    fg: "#ddd6fe",
    label: "별",
    path: "M32 14l5.5 11.5L50 27l-9 9 2 12.5L32 42l-11 6.5 2-12.5-9-9 12.5-1.5z",
  },
  a5: {
    bg: "#155e75",
    fg: "#cffafe",
    label: "물음표",
    path: "M24 24c0-5 4-8 8-8s8 3 8 8c0 5-8 6-8 12M32 44v2",
  },
  a6: {
    bg: "#831843",
    fg: "#fbcfe8",
    label: "하트",
    path: "M32 46S16 36 16 26a8 8 0 0116-4 8 8 0 0116 4c0 10-16 20-16 20z",
  },
};

/** 알 수 없는 키가 와도 화면이 비지 않게 첫 번째로 떨어진다. */
function presetOf(key: string) {
  return PRESETS[key] ?? PRESETS.a1;
}

/** 고르는 화면에서 읽어줄 이름. */
export function avatarLabel(key: string): string {
  return `${presetOf(key).label} 아바타`;
}

type Props = {
  shown: AvatarDisplay;
  /** 픽셀 크기. 정사각형이다. */
  size?: number;
  className?: string;
};

export function Avatar({ shown, size = 40, className = "" }: Props) {
  // 구글 사진 주소는 시간이 지나면 죽는다. 깨진 그림을 그대로 두지 않고
  // 아바타로 떨어뜨린다.
  const [photoFailed, setPhotoFailed] = useState(false);

  const usePhoto = shown.type === "photo" && !photoFailed;

  if (usePhoto) {
    return (
      // next/image 를 쓰지 않는다. 구글 도메인을 next.config 에 등록해야
      // 하고, 그 목록이 바뀌면 사진이 통째로 안 뜬다. 프로필 사진 한 장에
      // 그 위험을 지지 않는다.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={shown.url}
        alt=""
        width={size}
        height={size}
        onError={() => setPhotoFailed(true)}
        // referrerPolicy: 구글이 우리 주소를 받지 않게 한다. 안 주면
        // 사진 요청이 거절되는 경우도 있어 no-referrer 로 둔다.
        referrerPolicy="no-referrer"
        className={`shrink-0 rounded-full object-cover ${className}`}
      />
    );
  }

  const key = shown.type === "preset" ? shown.key : "a1";
  return <AvatarMark keyName={key} size={size} className={className} />;
}

/**
 * 아바타 하나를 그린다. 고르는 화면도 이걸 쓴다.
 *
 * 읽어주는 이름을 달지 않는다(aria-hidden). 지금 쓰는 자리마다 바로 옆에
 * 같은 뜻의 글자가 있어서, 이름을 달면 "아바타 3 터미널 아바타" 처럼 두 번
 * 읽힌다. 사진 쪽 img 도 같은 이유로 alt 가 비어 있다.
 */
export function AvatarMark({
  keyName,
  size = 40,
  className = "",
}: {
  keyName: string;
  size?: number;
  className?: string;
}) {
  const preset = presetOf(keyName);

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      aria-hidden="true"
      className={`shrink-0 rounded-full ${className}`}
    >
      <rect width="64" height="64" fill={preset.bg} />
      <path
        d={preset.path}
        fill="none"
        stroke={preset.fg}
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
