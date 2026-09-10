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

/** 인식이 끝난 이유. 화면이 이걸로 문구를 고른다. */
export type ListenOutcome =
  /** 글자를 받았다. heard 에 후보가 들어 있다. */
  | { type: "heard"; heard: string[] }
  /** 소리가 안 들렸다. 마이크가 조용했다. */
  | { type: "no-speech" }
  /** 마이크를 못 열었다. */
  | { type: "no-mic" }
  /** 권한이 거절됐다. */
  | { type: "denied" }
  /** 인식 서버에 못 닿았다. */
  | { type: "network" }
  /**
   * 결과도 에러도 없이 끝났다.
   *
   * abort() 로 끊었거나, 권한 창이 떠 있는 채로 시간이 다 된 경우다.
   * 에러 코드가 안 오는 경로가 실제로 있어서 따로 둔다.
   */
  | { type: "silent" };

/**
 * 한 번 듣는다.
 *
 * 취소 함수를 함께 돌려준다. 화면이 "그만" 을 누르거나 화면을 떠날 때
 * 부른다 - 안 끊으면 인식기가 살아남아 다음 판에 옛 결과가 끼어든다.
 */
export function listenOnce(
  onDone: (outcome: ListenOutcome) => void,
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
  const finish = (outcome: ListenOutcome) => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    onDone(outcome);
  };

  // 자체 타임아웃. start() 뒤에 아무 이벤트도 안 오는 구간이 실제로 있어서
  // (권한 창이 떠 있는 동안) 이게 없으면 "듣는 중" 이 영원히 돈다.
  const timer = setTimeout(() => {
    // abort 를 먼저 부른다. 안 끊으면 인식기가 살아서 나중에 결과를 던진다.
    try {
      recognition.abort();
    } catch {
      // 이미 끝난 인식기를 끊으면 던지는 브라우저가 있다. 무시해도 된다.
    }
    finish({ type: "silent" });
  }, timeoutMs);

  recognition.onresult = (event) => {
    const alternatives = event.results[0];
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
        return finish({ type: "no-speech" });
      case "audio-capture":
        return finish({ type: "no-mic" });
      case "not-allowed":
      case "service-not-allowed":
        return finish({ type: "denied" });
      case "network":
        return finish({ type: "network" });
      // aborted 는 우리가 끊은 것이라 위 타임아웃/취소가 이미 처리했다.
      default:
        return finish({ type: "silent" });
    }
  };

  // 결과도 에러도 없이 끝나는 경로가 있다(abort). 여기서 받는다.
  recognition.onend = () => finish({ type: "silent" });

  try {
    recognition.start();
  } catch {
    // 이미 돌고 있는 인식기를 다시 시작하면 던진다. 화면이 두 번 누른 경우다.
    finish({ type: "silent" });
  }

  return () => {
    try {
      recognition.abort();
    } catch {
      // 위와 같다.
    }
    finish({ type: "silent" });
  };
}
