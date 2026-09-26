/**
 * 문제 유형마다 지문과 보기가 용어(영어 낱말)인지, 영어인지.
 *
 * 용어는 고정폭, 한글(뜻·설명·상황)은 본문체로 그린다. 고정폭 글꼴
 * (JetBrains Mono)에는 한글 글자가 없어서, 한글을 고정폭으로 주면 OS 기본
 * 글꼴로 떨어져 굵고 뭉툭하게 나온다.
 *
 * 문제풀기(QuizBoard)와 한 판·일일공부·복습(QuestionCard)이 둘 다 여기를
 * 본다. 따로 정하던 때 두 화면이 달랐다 - 한쪽은 한글 지문(뜻·설명)을
 * 고정폭으로, 다른 쪽은 한글 보기(상황)를 고정폭으로 그렸고, 영어 보기는
 * 한쪽만 고정폭이었다.
 *
 *   유형          지문            보기
 *   meaning       용어            뜻(한글)
 *   term          뜻(한글)        용어
 *   description   설명(한글)      용어
 *   blank         문장(영어)      용어
 *   situation     문장(영어)      상황(한글)
 *
 * 문장 지문(blank·situation)은 **문장의 종류로 가른다.** 에러 메시지는
 * 고정폭, 실무 표현은 본문체다(promptIsMono). 익히기 목록·상세가 이미 이
 * 규칙이고, 디자인 가이드도 "단어·에러 메시지는 고정폭, 사람이 쓴 문장은
 * 가변폭" 이라고 적는다. 에러 메시지는 터미널에서 마주칠 모양 그대로 보여야
 * 익숙해지고, 실무 표현을 고정폭으로 쓰면 코드 주석처럼 보이고 폰에서 줄이
 * 늘어난다. 전에는 문제풀기만 고정폭, 한 판·일일공부·복습은 본문체로 화면
 * 마다 달랐다. 어느 쪽이든 영어이긴 하므로 lang 은 promptIsEnglish 로 붙인다.
 *
 * 모르는 유형은 용어가 아닌 것으로 본다. 본문체는 영어도 멀쩡히 그리지만,
 * 고정폭은 한글을 망가뜨린다.
 */
export function promptIsTerm(kind: string): boolean {
  return kind === "meaning";
}

const SENTENCE_PROMPT = new Set(["blank", "situation"]);

/**
 * 지문을 고정폭으로 그릴지. 용어(뜻 고르기)와 에러 메시지 문장만 고정폭이다.
 *
 * sentenceKind 는 서버가 문장 문제에 실어 보내는 문장 종류(error·phrase)다.
 * **모르면 본문체다.** 단어 문제에는 안 오고, 이 칸이 생기기 전에 저장된
 * 일일공부 문제(서버가 판에 저장해 두었다가 이어 풀 때 다시 준다)에도 없다.
 * 본문체는 영어도 멀쩡히 그리지만 고정폭은 한글을 망가뜨린다(위 원칙).
 */
export function promptIsMono(
  kind: string,
  sentenceKind?: string | null,
): boolean {
  return (
    promptIsTerm(kind) ||
    (SENTENCE_PROMPT.has(kind) && isErrorSentence(sentenceKind))
  );
}

/**
 * 문장 종류가 에러 메시지인지. 지문(promptIsMono)과 문제풀기 해설 카드가 같이
 * 쓴다 - 둘이 따로 비교하면 한 화면에서 같은 문장이 두 서체로 갈릴 수 있다.
 * 값은 백엔드 SentenceKind 그대로("error")라 대소문자를 맞춰 비교한다.
 */
export function isErrorSentence(sentenceKind?: string | null): boolean {
  return sentenceKind === "error";
}

/**
 * 지문이 문장인지(빈칸·상황). 문장은 단어 하나보다 훨씬 길어 여러 줄로
 * 감기므로, 굵기와 줄간격을 제목보다 한 단계 푼다. 고정폭을 가장 굵게
 * 여러 줄 그리면 글자가 뭉친다.
 */
export function promptIsSentence(kind: string): boolean {
  return SENTENCE_PROMPT.has(kind);
}

const ENGLISH_PROMPT = new Set(["meaning", "blank", "situation"]);

/**
 * 지문이 영어인지. lang="en" 을 붙일 자리다 - 없으면 화면 낭독기가 영어
 * 문장을 한국어 음성으로 읽는다.
 */
export function promptIsEnglish(kind: string): boolean {
  return ENGLISH_PROMPT.has(kind);
}

const TERM_CHOICES = new Set(["term", "description", "blank"]);

export function choicesAreTerms(kind: string): boolean {
  return TERM_CHOICES.has(kind);
}
