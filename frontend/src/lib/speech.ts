/**
 * 브라우저 음성 인식.
 *
 * 이 파일이 있는 이유는 Web Speech API 가 **조용히 실패하는 방식이 많아서**다.
 * 실제로 확인한 것들이고, 하나씩 안 막으면 화면이 멈춘 것처럼 보인다.
 *
 *   - `lang` 기본값이 빈 문자열이고, 그러면 브라우저 로케일을 쓴다. 이 앱을
 *     쓰는 사람은 대개 ko-KR 이라 **영어 단어를 한국어로 인식하려 든다.**
 *     그러면 채점이 전부 실패하는데, 원인이 화면 어디에도 안 보인다
 *   - `maxAlternatives` 기본값이 1 이다. 올리지 않으면 후보가 하나뿐이라
 *     "제대로 읽었는데 1등이 엉뚱한 것" 을 안내할 수 없다
 *   - `start()` 를 부른 뒤 **아무 이벤트도 안 오는 구간**이 있다. 권한 창이
 *     떠 있는 동안이 그렇다. 4초를 기다려도 start·audiostart·error·end 가
 *     하나도 안 왔다. 그래서 자체 타임아웃이 없으면 "듣는 중" 이 영원히 돈다
 *   - `abort()` 는 `onend` 만 부르고 `onerror` 를 안 부른다. 즉 **에러 코드
 *     없이 결과도 없이 끝나는 경로**가 있다
 *   - 안전한 컨텍스트가 아니면 `navigator.mediaDevices` 가 **통째로 없다**.
 *     속성이 false 인 게 아니라 객체가 없어서, 바로 짚으면 그 자리에서 터진다
 */

/** 인식기 타입. 브라우저 타입 정의에 없어서 필요한 만큼만 적는다. */
type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechResultEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  /** 마이크가 열렸다. 여기까지 안 오면 인식기가 시작을 못 한 것이다. */
  onaudiostart: (() => void) | null;
  /** 마이크에 소리가 들어왔다. 말인지 아닌지는 아직 모른다. */
  onsoundstart: (() => void) | null;
  /** 그 소리가 말로 판정됐다. */
  onspeechstart: (() => void) | null;
};

type SpeechResultEventLike = {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { length: number }>;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function recognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  // 접두사 없는 쪽을 먼저 본다. 나중에 표준이 자리잡으면 그쪽이 남는다.
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** 이 브라우저에서 소리내어 읽기가 되는가. */
export function speechSupported(): boolean {
  return recognitionCtor() !== null;
}

/**
 * 마이크를 쓸 수 있는 상태.
 *
 * **권한 창을 띄우지 않고** 알아낸다. 이게 이 화면 설계의 핵심이다 -
 * 한 번 거절하면 브라우저가 다시 안 묻기 때문에, 무턱대고 물어서
 * 거절당하면 되돌릴 방법이 사용자에게 없다.
 */
export type MicState =
  /** 이 브라우저가 음성 인식을 못 한다. */
  | "unsupported"
  /** 안전한 연결(https)이 아니라 마이크 자체를 못 연다. */
  | "insecure"
  /** 마이크가 달려 있지 않다. */
  | "no-device"
  /** 전에 거절했다. 브라우저가 다시 묻지 않는다. */
  | "denied"
  /** 이미 허용했다. */
  | "granted"
  /** 아직 안 물어봤다. 물어봐도 되는 상태. */
  | "prompt";

/**
 * 마이크 상태를 본다. 권한 창은 뜨지 않는다.
 *
 * 알 수 없으면 "prompt" 로 둔다. 상태를 모른다고 기능을 막으면 멀쩡한
 * 브라우저가 못 쓰게 된다 - 모르면 일단 물어보는 쪽이 맞다.
 */
export async function readMicState(): Promise<MicState> {
  if (!speechSupported()) return "unsupported";

  // mediaDevices 가 통째로 없는 경우가 있다(안전한 컨텍스트가 아닐 때).
  // 옵셔널 체이닝으로 짚지 않으면 여기서 터진다.
  if (typeof navigator === "undefined" || !navigator.mediaDevices) {
    // isSecureContext 로 사유를 가른다. https 가 아니라서인지, 아니면
    // 브라우저가 오래된 것인지에 따라 사용자가 할 수 있는 일이 다르다.
    return typeof window !== "undefined" && window.isSecureContext === false
      ? "insecure"
      : "unsupported";
  }

  // 장치가 있는지 먼저 본다. 권한을 물어봐도 마이크가 없으면 소용없다.
  // 데스크톱에서 실제로 흔하다.
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    if (!devices.some((d) => d.kind === "audioinput")) return "no-device";
  } catch {
    // 못 세면 그냥 넘어간다. 장치 목록은 참고이고, 진짜 판정은 아래 권한이다.
  }

  try {
    // name 을 캐스팅하는 이유: 표준 타입 정의에 microphone 이 없는 경우가
    // 있는데, 브라우저는 실제로 받는다.
    const status = await navigator.permissions.query({
      name: "microphone" as PermissionName,
    });
    if (status.state === "denied") return "denied";
    if (status.state === "granted") return "granted";
    return "prompt";
  } catch {
    // permissions 자체가 없거나 microphone 을 모르는 브라우저. 물어보면 된다.
    return "prompt";
  }
}

/**
 * 인식이 끝난 이유. 화면이 이걸로 문구를 고른다.
 *
 * **어디까지 갔는지로 가른다.** 인식기는 단계마다 신호를 주는데
 * (audiostart 마이크 열림 -> soundstart 소리 들어옴 -> speechstart 말로
 * 판정 -> result), 예전에는 그 셋을 안 보고 실패를 전부 "잘 못 알아들었어요"
 * 하나로 묶었다. 그러면 **마이크가 안 열린 것과 사용자가 작게 말한 것이
 * 같은 문구로 나온다** - 사용자가 할 수 있는 일이 정반대인데도.
 */
export type ListenOutcome =
  /** 글자를 받았다. heard 에 후보가 들어 있다. */
  | { type: "heard"; heard: string[] }
  /**
   * 인식기가 시작 자체를 못 했다. 마이크가 열린 신호(audiostart)조차 없다.
   *
   * 크롬에서 실제로 있다. start() 를 불러도 start·audiostart·error·end 가
   * 하나도 안 오고 조용히 죽는다. 이걸 "잘 못 알아들었어요" 로 말하면
   * 사용자는 자기 발음을 탓하며 계속 다시 시도한다.
   */
  | { type: "not-started" }
  /**
   * 마이크는 열렸는데 말을 한 번도 못 잡았다.
   *
   * **원인이 둘 섞여 있다.** 크롬이 다른 장치를 잡고 있거나 입력이 0인
   * 기계 쪽 문제일 수도 있고, 그냥 너무 작게 말한 것일 수도 있다. 크롬은
   * 소리 크기가 아니라 음성 구간 검출로 신호를 보내서 이 둘을 가를 수
   * 없다(위 onsoundstart 주석). 그래서 화면은 둘 다 말하고 MicCheck 로
   * 가르게 한다 - 기계 문제라고 단정하면 작게 말한 사람이 장치를 뒤진다.
   */
  | { type: "no-sound" }
  /** 소리는 들어왔는데 말로 인식되지 않았다. */
  | { type: "no-speech" }
  /** 마이크를 못 열었다. */
  | { type: "no-mic" }
  /** 권한이 거절됐다. */
  | { type: "denied" }
  /** 인식 서버에 못 닿았다. */
  | { type: "network" }
  /**
   * 소리까지는 들어왔는데 결과도 에러도 없이 끝났다(모르는 에러 코드 포함).
   *
   * 마이크가 안 열렸거나 소리가 안 들어온 채 끝나면 여기가 아니라
   * not-started·no-sound 로 간다(stalled). 에러 코드가 안 오는 경로가 실제로
   * 있어서 따로 둔다.
   */
  | { type: "silent" }
  /**
   * 사용자가 "그만" 을 눌렀거나 화면을 떠나 끊었다.
   *
   * **실패가 아니라서 silent 와 가른다.** 같은 값으로 두면 화면이 "잘 못
   * 알아들었어요, 또박또박 말해보세요" 를 띄워, 스스로 멈춘 사람에게 발음
   * 탓을 한다.
   */
  | { type: "cancelled" };

/**
 * 듣기가 어디까지 갔나.
 *
 *     starting  start() 를 불렀다. 아직 마이크가 열렸다는 신호가 없다
 *     open      마이크가 열렸다. 아직 소리가 안 들어왔다
 *     sound     소리가 들어왔다. 말인지는 모른다
 *     speech    말로 판정됐다
 */
export type ListenStage = "starting" | "open" | "sound" | "speech";

/** 단계가 가는 순서. 앞으로만 간다. */
const STAGES: ListenStage[] = ["starting", "open", "sound", "speech"];

/**
 * 한 번 듣는다.
 *
 * 취소 함수를 함께 돌려준다. 화면이 "그만" 을 누르거나 화면을 떠날 때
 * 부른다 - 안 끊으면 인식기가 살아남아 다음 판에 옛 결과가 끼어든다.
 */
export function listenOnce(
  onDone: (outcome: ListenOutcome) => void,
  /**
   * 어디까지 갔는지 알린다. 화면이 "듣고 있어요" 대신 실제 단계를 보여준다.
   *
   * 이게 있어야 사용자가 **말하는 도중에** 마이크가 먹는지 안다. 끝나고
   * 문구만 보면 8초를 헛되이 쓴 뒤다.
   */
  onStage?: (stage: ListenStage) => void,
  /** 이 시간 안에 아무 신호도 없으면 포기한다. */
  timeoutMs = 8000,
): () => void {
  const Ctor = recognitionCtor();
  if (!Ctor) {
    onDone({ type: "silent" });
    return () => {};
  }

  const recognition = new Ctor();

  // 반드시 지정한다. 비워두면 브라우저 로케일(대개 ko-KR)로 인식한다.
  recognition.lang = "en-US";
  // 후보를 여러 개 받는다. 기본값이 1 이라 안 올리면 near 안내를 못 만든다.
  recognition.maxAlternatives = 5;
  // 한 번만 듣고 끝낸다. 켜두면 사용자가 말을 멈춰도 계속 듣는다.
  recognition.continuous = false;
  recognition.interimResults = false;

  // 한 번만 끝낸다. onresult 뒤에 onend 가 또 오므로, 안 막으면 결과를
  // 보낸 뒤 "결과 없음" 이 덮어쓴다.
  let settled = false;

  /** 어디까지 갔나. 끝났을 때 이유를 가르는 근거다. */
  let stage: ListenStage = "starting";
  const reach = (next: ListenStage) => {
    // **끝난 뒤의 신호와 뒤로 가는 신호는 버린다.** 끊긴 인식기가 늦게 쏜
    // audiostart 를 알리면 곧바로 다시 누른 판의 "마이크를 여는 중" 을 덮고,
    // 말까지 간 뒤 audiostart 가 한 번 더 와서 open 으로 돌아가면 끝날 때
    // no-sound 로 떨어져 말을 한 사람에게 MicCheck 가 뜬다.
    if (settled || STAGES.indexOf(next) <= STAGES.indexOf(stage)) return;
    stage = next;
    clearTimeout(startGuard);
    onStage?.(next);
  };

  /** 단계별 신호가 없이 끝났을 때 그 자리에 맞는 이유를 고른다. */
  const stalled = (): ListenOutcome => {
    if (stage === "starting") return { type: "not-started" };
    if (stage === "open") return { type: "no-sound" };
    return { type: "silent" };
  };

  const finish = (outcome: ListenOutcome) => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    clearTimeout(startGuard);
    onDone(outcome);
  };

  /**
   * 이유를 먼저 정하고 **그다음에** 인식기를 끊는다.
   *
   * 순서가 거꾸로면 abort() 안에서 onend·onerror 를 곧바로 부르는 구현에서
   * 그쪽이 먼저 끝내 버린다. 사용자가 "그만" 을 눌렀는데 "마이크에 소리가
   * 안 들어와요" 가 뜨고 MicCheck 까지 열리는 식이다. 크롬은 이벤트를 미뤄
   * 보내서 지금은 안 드러나지만, 순서에 기대는 약점이라 순서를 없앤다.
   */
  const settleThenAbort = (outcome: ListenOutcome) => {
    finish(outcome);
    try {
      recognition.abort();
    } catch {
      // 이미 끝난 인식기를 끊으면 던지는 브라우저가 있다. 무시해도 된다.
    }
  };

  /**
   * 마이크가 열리는 것만 따로 짧게 기다린다.
   *
   * 열리는 데는 한참 안 걸린다 - 크롬에서 audiostart 는 200ms 안에 온다.
   * 안 오면 앞으로도 안 오므로, 전체 타임아웃(8초)까지 기다리게 두면
   * 사용자가 8초 동안 아무 일도 안 일어나는 화면에 대고 말한다.
   */
  const startGuard = setTimeout(() => {
    if (stage !== "starting") return;
    settleThenAbort({ type: "not-started" });
  }, 2500);

  // 자체 타임아웃. 마이크는 열렸는데 그 뒤로 아무 이벤트도 안 오는 구간이
  // 있어서, 이게 없으면 "듣는 중" 이 영원히 돈다. 열리지도 않은 경우는 위
  // 시작 감시가 먼저 끊는다.
  const timer = setTimeout(() => {
    // 끊기는 반드시 한다. 안 끊으면 인식기가 살아서 나중에 결과를 던진다.
    settleThenAbort(stalled());
  }, timeoutMs);

  // 마이크가 열렸다. 여기까지 와야 인식기가 실제로 도는 것이다.
  recognition.onaudiostart = () => reach("open");
  // **크롬은 soundstart 와 speechstart 를 한꺼번에 쏜다.** 소리 크기가 아니라
  // 음성 구간 검출(endpointer)이 말을 잡았을 때 둘을 연달아 보낸다. 그래서
  // 크롬에서는 sound 에만 머무는 순간이 없고, "마이크는 열렸는데 말을 못
  // 잡음" 에는 소리가 아예 안 들어온 경우와 **너무 작게 말한 경우가 같이
  // 들어간다.** 둘을 따로 받는 것은 다른 엔진이 나눠 보낼 때를 위해서다.
  recognition.onsoundstart = () => reach("sound");
  recognition.onspeechstart = () => reach("speech");

  recognition.onresult = (event) => {
    // 빈 결과 이벤트를 주는 구현이 있다. 그대로 짚으면 여기서 던지고,
    // 끝낼 사람이 없어 8초 타임아웃까지 "듣는 중" 이 돈다.
    const alternatives = event.results?.[0];
    if (!alternatives) return finish({ type: "no-speech" });
    const heard: string[] = [];
    for (let i = 0; i < alternatives.length; i += 1) {
      const said = alternatives[i]?.transcript?.trim();
      if (said) heard.push(said);
    }
    finish(heard.length ? { type: "heard", heard } : { type: "no-speech" });
  };

  recognition.onerror = (event) => {
    // 인식기가 주는 코드를 화면이 쓸 갈래로 옮긴다. 코드를 그대로 위로
    // 올리면 문구를 정하는 곳이 브라우저 어휘를 알아야 한다.
    switch (event.error) {
      case "no-speech":
        // 말을 한 번도 못 잡았으면 no-sound 다. 마이크가 열렸다는 신호조차
        // 없이 이 에러가 와도 마찬가지다 - 그 상태를 "소리는 들어왔는데
        // 말이 아님" 이라고 하면 사실과 반대다.
        return finish(
          stage === "starting" || stage === "open"
            ? { type: "no-sound" }
            : { type: "no-speech" },
        );
      case "audio-capture":
        return finish({ type: "no-mic" });
      case "not-allowed":
      case "service-not-allowed":
        return finish({ type: "denied" });
      case "network":
        return finish({ type: "network" });
      // aborted 는 우리가 끊은 것이면 위 타임아웃/취소가 이미 처리했다.
      //
      // 모르는 코드(language-not-supported, 브라우저가 스스로 끊은 aborted)는
      // 간 자리로 가른다. 그냥 silent 로 두면 마이크가 열리기도 전에 온
      // 에러에도 "잘 못 알아들었어요" 가 떠 발음 탓을 한다.
      default:
        return finish(stalled());
    }
  };

  // 결과도 에러도 없이 끝나는 경로가 있다(abort). 여기서 받는다.
  // 어디까지 갔는지에 따라 이유가 다르다.
  recognition.onend = () => finish(stalled());

  try {
    recognition.start();
  } catch {
    // 이미 돌고 있는 인식기를 다시 시작하면 던진다. 화면이 두 번 누른
    // 경우이고, 시작을 못 한 것이 맞다.
    finish({ type: "not-started" });
  }

  // 사용자가 "그만" 을 누른 것은 실패가 아니다. 어디까지 갔든 cancelled 다.
  return () => settleThenAbort({ type: "cancelled" });
}
