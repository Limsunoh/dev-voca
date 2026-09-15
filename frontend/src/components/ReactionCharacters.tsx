/**
 * 채점 연출에 나오는 캐릭터 둘. 부장님과 학생, 3등신.
 *
 * **디자인 원본을 옮긴 것이다.** 원본은 `assets/characters.js` 이고 문자열을
 * 뱉는 함수였다(`DV_CHAR.boss("neutral")`). 그것을 JSX 로 옮긴 이유는 둘이다.
 *
 * 하나. 원본은 그라디언트 id 를 모듈 최상위 `let uid = 0` 카운터로 만든다.
 * 이 저장소에서 그대로 쓰면 **서버 렌더와 클라이언트 렌더의 카운터가 갈려
 * hydration 이 어긋난다**. 'use client' 를 붙여도 마찬가지다 - 클라이언트
 * 컴포넌트도 서버에서 한 번 그려진다. 원본은 브라우저에서만 도는
 * 스크립트라 그 문제가 없었다.
 * 그래서 id 를 prop(gid)으로 받고, 부르는 쪽이 useId() 로 만든다.
 *
 * 둘. 문자열을 받으면 dangerouslySetInnerHTML 이 필요한데, 그러면 id 가 이미
 * 문자열에 박혀 나와 위 방법을 쓸 수 없다. 두 판단이 한 이유에서 나온다.
 * (이 저장소가 그것을 안 쓰는 것은 Reading.tsx 주석에도 적혀 있다.)
 *
 * **원본 구조를 함수 단위로 유지했다.** defs · eye · legs · boss · student 가
 * 원본과 같은 자리에 있다. 원본이 바뀌면 손으로 맞춰야 하는데, 구조가 같으면
 * 어디를 고칠지 찾기 쉽다.
 *
 * 좌표계: **발 가운데가 (0,0) 이고 위가 음수다.** 키가 약 195 다. 부르는 쪽이
 * translate 로 세울 자리를 정한다.
 *
 * 표정은 **셋을 다 그려 넣고 CSS 가 하나만 켠다**. 원본이 그렇게 하는 이유는
 * 표정을 바꿀 때 DOM 을 다시 만들지 않아도 되기 때문이고, 연출 중간(66%)에
 * 표정이 바뀌는 것을 키프레임으로 처리할 수 있다.
 */

/* expr 은 클래스 이름(`char expr-<값>`)으로만 나간다. 표정을 실제로 켜고
   끄는 것은 globals.css 의 `.vx .char [data-x=...]` 키프레임이라, expr 로
   표정이 바뀌지는 않는다. 원본 구조를 그대로 두려고 남긴 인자다 - 넘긴
   값으로 뭔가 달라질 거라고 기대하지 말 것. */

/** 윤곽선 잉크. 원본의 INK. */
const INK = "#2A2320";

/**
 * 윤곽선 속성. 원본의 `o(w)` 헬퍼와 같다.
 *
 * 객체를 펼쳐 쓴다(`{...outline()}`). 같은 넷을 스물 몇 군데에 적어야 해서
 * 하나씩 쓰면 그 자체가 읽기를 방해한다.
 */
function outline(width = 1.6) {
  return {
    stroke: INK,
    strokeWidth: width,
    strokeLinejoin: "round" as const,
    strokeLinecap: "round" as const,
  };
}

/**
 * 그라디언트 정의. gid 로 이름을 가른다.
 *
 * 살색·머리색·옷색에 각각 그라디언트를 두는 것은 3등신 캐릭터를 평면으로
 * 칠하면 종이처럼 보이기 때문이다. 원본의 판단을 그대로 옮겼다.
 */
function Defs({
  gid,
  skin,
  skinDark,
  hair,
  hairLight,
  cloth,
  clothDark,
}: {
  gid: string;
  skin: string;
  skinDark: string;
  hair: string;
  hairLight: string;
  cloth: string;
  clothDark: string;
}) {
  return (
    <defs>
      <linearGradient id={`${gid}-skin`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor={skin} />
        <stop offset="1" stopColor={skinDark} />
      </linearGradient>
      <linearGradient id={`${gid}-hair`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor={hairLight} />
        <stop offset=".55" stopColor={hair} />
      </linearGradient>
      <linearGradient id={`${gid}-cloth`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor={cloth} />
        <stop offset="1" stopColor={clothDark} />
      </linearGradient>
      {/* 볼 홍조. 가운데가 진하고 밖으로 사라진다. */}
      <radialGradient id={`${gid}-blush`} cx=".5" cy=".5" r=".5">
        <stop offset="0" stopColor="#F58A8A" stopOpacity=".55" />
        <stop offset="1" stopColor="#F58A8A" stopOpacity="0" />
      </radialGradient>
    </defs>
  );
}

/**
 * 눈 하나. 흰자·홍채·동공·하이라이트 둘·윗눈꺼풀.
 *
 * 하이라이트를 둘 두는 것이 애니 스타일의 핵심이다. 하나만 두면 눈이
 * 유리구슬처럼 보이고, 없으면 죽은 눈이 된다.
 */
function Eye({
  cx,
  cy,
  iris,
  w = 10,
  h = 12,
  look = 0,
}: {
  cx: number;
  cy: number;
  iris: string;
  w?: number;
  h?: number;
  look?: number;
}) {
  return (
    <>
      <ellipse cx={cx} cy={cy} rx={w / 2} ry={h / 2} fill="#fff" />
      <ellipse
        cx={cx + look}
        cy={cy + 1}
        rx={w / 2 - 1.5}
        ry={h / 2 - 1.5}
        fill={iris}
      />
      <ellipse
        cx={cx + look}
        cy={cy + 2}
        rx={w / 4}
        ry={h / 4 + 0.5}
        fill={INK}
      />
      <circle cx={cx + look - 2} cy={cy - 2} r="1.8" fill="#fff" />
      <circle cx={cx + look + 1.5} cy={cy + 3} r=".9" fill="#fff" opacity=".8" />
      {/* 윗눈꺼풀. 굵은 선 하나가 눈매를 만든다. */}
      <path
        d={`M${cx - w / 2 - 1} ${cy - h / 2 + 2}q${w / 2 + 1} -${h / 2 + 1} ${w + 2} 0`}
        fill="none"
        {...outline(2.4)}
      />
    </>
  );
}

/** 감은 눈. 웃는 표정에 쓴다. */
function EyeSmile({ cx, cy, w = 10 }: { cx: number; cy: number; w?: number }) {
  return (
    <path
      d={`M${cx - w / 2} ${cy}q${w / 2} -6 ${w} 0`}
      fill="none"
      {...outline(2.4)}
    />
  );
}

/** 질끈 감은 눈. 아픈 표정에 쓴다. */
function EyeSquint({ cx, cy, dir = 1 }: { cx: number; cy: number; dir?: number }) {
  return (
    <path
      d={`M${cx - 5 * dir} ${cy - 5}l${5 * dir} 5 ${-5 * dir} 5`}
      fill="none"
      {...outline(2.4)}
    />
  );
}

/**
 * 두 다리. CSS 가 `.legA`·`.legB` 를 번갈아 돌려 걷게 만든다.
 *
 * 클래스 이름을 원본 그대로 둔다 - 키프레임(vx-step-a/b)이 그 이름을 찾는다.
 */
function Legs({
  cloth,
  shoe,
  hipY,
  gap,
  len,
  w = 15,
}: {
  cloth: string;
  shoe: React.ReactNode;
  hipY: number;
  gap: number;
  len: number;
  w?: number;
}) {
  const leg = (cls: string) => (
    <g className={cls}>
      <path
        d={`M${-w / 2} 0h${w}v${len}a${w / 2} ${w / 2} 0 0 1 ${-w} 0z`}
        fill={cloth}
        {...outline()}
      />
      {shoe}
    </g>
  );
  return (
    <>
      <g transform={`translate(${-gap},${hipY})`}>{leg("legA")}</g>
      <g transform={`translate(${gap},${hipY})`}>{leg("legB")}</g>
    </>
  );
}

/** 부장님 표정. */
export type BossExpr = "neutral" | "smile" | "stern";
/** 학생 표정. */
export type StudentExpr = "idle" | "happy" | "ouch";

/**
 * 부장님. 반백 머리에 안경과 콧수염, 남색 재킷.
 *
 * 오른팔만 `.arm` 으로 빼서 CSS 가 돌린다(쓰다듬기·콩). 머리 아래 몸통 위에
 * 두는 순서가 중요하다 - 팔이 머리를 덮으면 손이 얼굴을 가린다.
 */
export function Boss({ gid, expr }: { gid: string; expr: BossExpr }) {
  const iris = "#4E6A7A";
  const shoe = (
    <>
      <path
        d="M-10 44h20a6 6 0 0 1 6 6v3h-32v-3a6 6 0 0 1 6-6z"
        fill="#3A3230"
        {...outline()}
      />
      <path d="M-6 47h12" stroke="#5A4E4A" strokeWidth="1.2" />
    </>
  );

  return (
    <g className={`char expr-${expr}`}>
      <Defs
        gid={gid}
        skin="#F6D6BE"
        skinDark="#E8B896"
        hair="#6F7680"
        hairLight="#B9C0C8"
        cloth="#2F3A55"
        clothDark="#1E2740"
      />
      <Legs cloth="#3A4258" shoe={shoe} hipY={-62} gap={11} len={44} />

      {/* 몸통: 재킷 */}
      <path
        d="M-33 -110a33 33 0 0 1 66 0v40a33 33 0 0 1 -66 0z"
        fill={`url(#${gid}-cloth)`}
        {...outline()}
      />
      {/* 와이셔츠 + 넥타이 */}
      <path
        d="M-14 -112l14 34 14-34a20 20 0 0 1 -28 0z"
        fill="#F8F6F1"
        {...outline(1.2)}
      />
      <path d="M0 -110l5 8-5 30-5-30z" fill="#E28F2A" {...outline(1.2)} />
      <path d="M0 -110l5 8-5 30z" fill="#C9761C" />
      {/* 재킷 라펠 */}
      <path
        d="M-14 -112l-8 30 14 -8zM14 -112l8 30-14-8z"
        fill="#1E2740"
        {...outline(1.2)}
      />
      {/* 배 하이라이트. 평면으로 두면 재킷이 판자처럼 보인다. */}
      <path
        d="M-30 -80q-3 14 2 24"
        fill="none"
        stroke="#fff"
        strokeWidth="2"
        opacity=".18"
      />
      {/* 왼팔. 굵은 선을 두 겹 겹쳐 소매 테두리를 만든다. */}
      <path
        d="M-32 -100q-10 20 -5 42"
        fill="none"
        stroke="#1E2740"
        strokeWidth="15"
        strokeLinecap="round"
      />
      <path
        d="M-32 -100q-10 20 -5 42"
        fill="none"
        stroke="#2F3A55"
        strokeWidth="11"
        strokeLinecap="round"
      />
      <circle cx="-36" cy="-56" r="9" fill={`url(#${gid}-skin)`} {...outline()} />
      {/* 목 */}
      <rect x="-8" y="-128" width="16" height="16" fill="#E8B896" />
      {/* 오른팔(움직이는 쪽). 머리 아래·몸통 위에 둔다. */}
      <g transform="translate(32,-102)">
        <g className="arm">
          <path d="M0 0v42" stroke="#1E2740" strokeWidth="15" strokeLinecap="round" />
          <path d="M0 0v42" stroke="#2F3A55" strokeWidth="11" strokeLinecap="round" />
          <circle cx="0" cy="50" r="9.5" fill={`url(#${gid}-skin)`} {...outline()} />
        </g>
      </g>
      {/* 머리 */}
      <circle cx="-34" cy="-152" r="6" fill={`url(#${gid}-skin)`} {...outline()} />
      <circle cx="34" cy="-152" r="6" fill={`url(#${gid}-skin)`} {...outline()} />
      <path
        d="M-34 -150c0-24 12-40 34-40s34 16 34 40c0 20-14 34-34 34s-34-14-34-34z"
        fill={`url(#${gid}-skin)`}
        {...outline()}
      />
      {/* 반백 머리. 이마를 넓게 두고 옆으로 빗어 넘긴다. */}
      <path
        d="M-34 -156c-2-22 12-38 34-38 16 0 28 8 32 22-6-6-16-8-26-4-4-6-12-8-18-4-10 4-18 12-22 24z"
        fill={`url(#${gid}-hair)`}
        {...outline()}
      />
      <path
        d="M-34 -152c-3 8-3 18 0 26-4-8-5-18 0-26zM34 -152c3 8 3 18 0 26 4-8 5-18 0-26z"
        fill="#6F7680"
        {...outline()}
      />
      <path
        d="M-18 -184q10-6 22-2"
        fill="none"
        stroke="#DDE2E8"
        strokeWidth="2.4"
        strokeLinecap="round"
        opacity=".9"
      />
      <path
        d="M-8 -190q8-2 16 2"
        fill="none"
        stroke="#DDE2E8"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity=".7"
      />
      {/* 귀 안쪽 */}
      <path
        d="M-35 -154q-2 3 0 6M35 -154q2 3 0 6"
        fill="none"
        stroke="#C9977A"
        strokeWidth="1.4"
      />
      {/* 코 */}
      <path
        d="M2 -146q4 6 -1 9"
        fill="none"
        stroke="#B98468"
        strokeWidth="1.6"
        strokeLinecap="round"
      />

      {/* 표정 셋을 다 그려두고 CSS 가 하나만 켠다. data-x 이름을 바꾸면
          globals.css 의 `.char [data-x="..."]` 규칙과 어긋난다. */}
      <g data-x="neutral">
        <Eye cx={-13} cy={-152} iris={iris} />
        <Eye cx={13} cy={-152} iris={iris} />
        <path
          d="M-20 -164q7-3 14 0M6 -164q7-3 14 0"
          fill="none"
          {...outline(2.6)}
        />
        <path d="M-6 -134q6 2 12 0" fill="none" {...outline(2)} />
      </g>
      <g data-x="smile">
        <EyeSmile cx={-13} cy={-151} />
        <EyeSmile cx={13} cy={-151} />
        <path
          d="M-20 -165q7-4 14 -1M6 -166q7-3 14 1"
          fill="none"
          {...outline(2.6)}
        />
        <path d="M-9 -136q9 8 18 0" fill="none" {...outline(2.2)} />
        <circle cx="-23" cy="-142" r="7" fill={`url(#${gid}-blush)`} />
        <circle cx="23" cy="-142" r="7" fill={`url(#${gid}-blush)`} />
      </g>
      <g data-x="stern">
        <Eye cx={-13} cy={-151} iris={iris} w={10} h={9} />
        <Eye cx={13} cy={-151} iris={iris} w={10} h={9} />
        <path d="M-21 -163l15 4M21 -163l-15 4" fill="none" {...outline(2.8)} />
        <path d="M-7 -134h14" fill="none" {...outline(2.2)} />
        {/* 이마 주름. 굳은 표정을 만드는 두 줄이다. */}
        <path
          d="M-4 -172l3 4M1 -172l3 4"
          fill="none"
          stroke="#8A6B60"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </g>

      {/* 안경. 표정 위에 얹어야 렌즈가 눈을 덮는다. */}
      <path
        d="M-26 -155h22a4 4 0 0 1 4 4v6a6 6 0 0 1 -6 6h-18a6 6 0 0 1 -6 -6v-6a4 4 0 0 1 4 -4zM4 -155h22a4 4 0 0 1 4 4v6a6 6 0 0 1 -6 6h-18a6 6 0 0 1 -6 -6v-6a4 4 0 0 1 4 -4z"
        fill="rgba(255,255,255,.18)"
        {...outline(1.8)}
      />
      <path
        d="M0 -150h0M-28 -151l-7-2M28 -151l7-2"
        fill="none"
        {...outline(1.8)}
      />
      <path d="M-1 -151h2" {...outline(1.8)} />
      <path
        d="M-24 -152l6-3M6 -152l6-3"
        fill="none"
        stroke="#fff"
        strokeWidth="1.4"
        opacity=".7"
      />
      {/* 콧수염 */}
      <path
        d="M-11 -139q5 3 11 1q6 2 11-1q-4 6-11 5q-7 1-11-5z"
        fill="#6F7680"
        {...outline(1.2)}
      />
    </g>
  );
}

/**
 * 학생. 짧은 머리에 파란 후드티.
 *
 * 부장님과 달리 팔이 둘 다 고정이다. 학생은 맞는 쪽이라 팔을 움직일 일이
 * 없고, 대신 몸 전체가 `.stu` 로 눌리거나 튄다(vx-happy·vx-ouch).
 */
export function Student({ gid, expr }: { gid: string; expr: StudentExpr }) {
  const iris = "#5A3E2E";
  const shoe = (
    <>
      <path
        d="M-10 46h20a6 6 0 0 1 6 6v3h-32v-3a6 6 0 0 1 6-6z"
        fill="#F8F6F1"
        {...outline()}
      />
      <path d="M-10 50h32" stroke="#D8D2C8" strokeWidth="1.4" />
      <path d="M-6 47h6" stroke="#2A4A7B" strokeWidth="1.6" />
    </>
  );

  return (
    <g className={`char expr-${expr}`}>
      <Defs
        gid={gid}
        skin="#F8DCC6"
        skinDark="#EDBE9E"
        hair="#3E2A22"
        hairLight="#6B4A3A"
        cloth="#3B6BA8"
        clothDark="#2A4A7B"
      />
      <Legs cloth="#2C3E66" shoe={shoe} hipY={-64} gap={10} len={46} w={14} />

      {/* 후드 뒤. 몸통보다 먼저 그려야 목 뒤로 들어간다. */}
      <path d="M-30 -122q30-18 60 0v16h-60z" fill="#2A4A7B" {...outline()} />
      {/* 후드티 */}
      <path
        d="M-30 -112a30 30 0 0 1 60 0v40a30 30 0 0 1 -60 0z"
        fill={`url(#${gid}-cloth)`}
        {...outline()}
      />
      {/* 후드 목선 + 끈 */}
      <path
        d="M-18 -114q18 12 36 0"
        fill="none"
        stroke="#2A4A7B"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <path
        d="M-7 -110v20M7 -110v20"
        fill="none"
        stroke="#F8F6F1"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <circle cx="-7" cy="-89" r="2" fill="#F8F6F1" />
      <circle cx="7" cy="-89" r="2" fill="#F8F6F1" />
      {/* 주머니 */}
      <path
        d="M-18 -80h36v12a6 6 0 0 1 -6 6h-24a6 6 0 0 1 -6 -6z"
        fill="#2A4A7B"
        {...outline(1.2)}
      />
      {/* 팔 둘. 부장님과 같은 두 겹 기법. */}
      <path
        d="M-29 -100q-10 18 -6 40"
        fill="none"
        stroke="#2A4A7B"
        strokeWidth="15"
        strokeLinecap="round"
      />
      <path
        d="M-29 -100q-10 18 -6 40"
        fill="none"
        stroke="#3B6BA8"
        strokeWidth="11"
        strokeLinecap="round"
      />
      <circle cx="-34" cy="-58" r="9" fill={`url(#${gid}-skin)`} {...outline()} />
      <path
        d="M29 -100q10 18 6 40"
        fill="none"
        stroke="#2A4A7B"
        strokeWidth="15"
        strokeLinecap="round"
      />
      <path
        d="M29 -100q10 18 6 40"
        fill="none"
        stroke="#3B6BA8"
        strokeWidth="11"
        strokeLinecap="round"
      />
      <circle cx="34" cy="-58" r="9" fill={`url(#${gid}-skin)`} {...outline()} />
      {/* 목 */}
      <rect x="-8" y="-128" width="16" height="16" fill="#EDBE9E" />
      {/* 머리 */}
      <circle cx="-32" cy="-150" r="6" fill={`url(#${gid}-skin)`} {...outline()} />
      <circle cx="32" cy="-150" r="6" fill={`url(#${gid}-skin)`} {...outline()} />
      <path
        d="M-32 -148c0-24 12-40 32-40s32 16 32 40c0 20-13 34-32 34s-32-14-32-34z"
        fill={`url(#${gid}-skin)`}
        {...outline()}
      />
      {/* 머리카락. 볼륨 있는 캡에 앞머리 결을 갈라 넣는다. */}
      <path
        d="M-34 -150c-4-30 14-46 34-46s38 16 34 46c-1 6-3 10-5 12 3-12-1-22-8-26-2 6-6 10-10 12 0-6-3-10-6-12-4 4-10 6-14 4-5-2-9-6-10-10-6 6-8 16-6 24-3-2-7-8-9-4z"
        fill={`url(#${gid}-hair)`}
        {...outline()}
      />
      <path
        d="M-33 -146c-3 8-3 18 0 26-4-8-6-18 0-26zM33 -146c3 8 3 18 0 26 4-8 6-18 0-26z"
        fill="#3E2A22"
        {...outline()}
      />
      <path
        d="M-16 -186q10-6 22-3"
        fill="none"
        stroke="#8C6A58"
        strokeWidth="2.6"
        strokeLinecap="round"
        opacity=".85"
      />
      <path
        d="M-6 -192q8-2 14 1"
        fill="none"
        stroke="#8C6A58"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity=".6"
      />
      <path
        d="M-22 -164q6 8 12 2M10 -164q6 8 12 2"
        fill="none"
        stroke="#2A1C16"
        strokeWidth="1.2"
        opacity=".5"
      />
      {/* 귀 안쪽 / 코 */}
      <path
        d="M-33 -152q-2 3 0 6M33 -152q2 3 0 6"
        fill="none"
        stroke="#CF9C7E"
        strokeWidth="1.4"
      />
      <path
        d="M1 -144q3 5 -1 7"
        fill="none"
        stroke="#C4886A"
        strokeWidth="1.4"
        strokeLinecap="round"
      />

      {/* 표정 셋. 부장님과 같은 규칙이다. */}
      <g data-x="idle">
        <Eye cx={-13} cy={-150} iris={iris} w={12} h={14} />
        <Eye cx={13} cy={-150} iris={iris} w={12} h={14} />
        <path
          d="M-20 -164q7-3 14 0M6 -164q7-3 14 0"
          fill="none"
          {...outline(2.2)}
        />
        <path d="M-6 -132q6 4 12 0" fill="none" {...outline(2)} />
        <circle cx="-24" cy="-140" r="7" fill={`url(#${gid}-blush)`} />
        <circle cx="24" cy="-140" r="7" fill={`url(#${gid}-blush)`} />
      </g>
      <g data-x="happy">
        <EyeSmile cx={-13} cy={-149} w={12} />
        <EyeSmile cx={13} cy={-149} w={12} />
        <path
          d="M-20 -166q7-4 14 -1M6 -167q7-3 14 1"
          fill="none"
          {...outline(2.2)}
        />
        <path d="M-10 -136q10 12 20 0z" fill="#E2665A" {...outline(1.8)} />
        <path d="M-7 -135q7 4 14 0" fill="#fff" opacity=".9" />
        <circle cx="-24" cy="-140" r="8" fill={`url(#${gid}-blush)`} />
        <circle cx="24" cy="-140" r="8" fill={`url(#${gid}-blush)`} />
        {/* 기쁨을 나타내는 반짝임. 얼굴 밖으로 튀는 네 줄이다. */}
        <path
          d="M-30 -168l-3-4M30 -168l3-4M-33 -160h-4M33 -160h4"
          fill="none"
          stroke="#F2A93B"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </g>
      <g data-x="ouch">
        <EyeSquint cx={-13} cy={-150} />
        <EyeSquint cx={13} cy={-150} dir={-1} />
        <path d="M-20 -166l14 5M20 -166l-14 5" fill="none" {...outline(2.4)} />
        <path d="M-7 -132q7-6 14 0" fill="none" {...outline(2.2)} />
        {/* 땀방울. 오른쪽 관자놀이에 하나. */}
        <path
          d="M32 -172q7 7 0 14q-7-7 0-14z"
          fill="#9CD3F5"
          {...outline(1.4)}
        />
        <path
          d="M30 -166q2 3 0 6"
          stroke="#fff"
          strokeWidth="1.2"
          fill="none"
        />
        <circle cx="-24" cy="-140" r="7" fill={`url(#${gid}-blush)`} />
        <circle cx="24" cy="-140" r="7" fill={`url(#${gid}-blush)`} />
      </g>
    </g>
  );
}
