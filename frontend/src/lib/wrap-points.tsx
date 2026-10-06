import type { ReactNode } from "react";

/**
 * 빈칸 없이 긴 덩어리(URL·파일 경로·점으로 이은 이름)에 줄바꿈해도 되는
 * 자리(<wbr>)를 넣는다.
 *
 * 전역 `overflow-wrap: anywhere`(globals.css)가 가로 스크롤을 막으려고 한 줄에
 * 안 들어가는 낱말을 아무 글자에서나 자른다. 그래서
 * "'https://github.com/acme/demo.git'" 가 폰에서 "de|mo.git" 처럼 낱말
 * 가운데서 끊긴다. 자리를 알려 주면 브라우저가 그쪽을 먼저 쓴다.
 *
 * <wbr> 은 빈칸과 같은 급의 줄바꿈 자리라, 여러 줄 글에서는 한 줄에 들어갈
 * 짧은 덩어리도 줄 끝에 걸리면 쪼갠다("src/app." / "py"). 그래서 20자를
 * 넘는 덩어리에만 넣는다. 390px 지문 한 줄은 고정폭 25자 안팎이라 21~25자는
 * 대개 한 줄에 들어가지만, 360px 폰이나 큰 글자 지문(3xl)에서는 넘친다.
 * 넘쳐서 아무 글자에서나 잘리는 것보다 경계에서 끊기는 편이 낫다고 봤다.
 *
 * 넣는 자리(`/`·`.` 는 URL 을 끊는 흔한 관행대로):
 * - `/` 는 뒤에서 끊는다. 다음 글자가 경로에 쓰는 글자(영숫자 `._~-`)일
 *   때만 끊고, "//" 사이와 끝 `/` 다음 닫는 따옴표 앞은 끊지 않는다.
 * - `.` 는 앞에서 끊는다. 줄 끝에 남은 점이 마침표로 읽히지 않게.
 *   앞이 영숫자이고 뒤가 영문자일 때만 끊어서, "65.0"·"v2.0.0" 같은 숫자,
 *   ".git" 같은 앞 점, 문장 끝 마침표는 건드리지 않는다.
 * - 소문자 다음 대문자 앞에서 끊는다. "UnsupportedClassVersionError:" 처럼
 *   점 없이도 한 줄을 넘는 이름이 "…VersionE" / "rror:" 로 잘리지 않게.
 * - `::` 와 `_` 뒤에서 끊는다. "net::ERR_CONNECTION_REFUSED" 가
 *   "net::" / "ERR_" / "CONNECTION_" / "REFUSED" 로 끊긴다. 콜론 하나
 *   ("localhost:8080")는 포트가 갈라지므로 끊지 않는다. 밑줄은 영숫자 바로
 *   다음의 한 개만 본다. "__init__" 이나 빈칸 표시 "____" 는 그대로 둔다.
 *
 * 넣을 자리가 없으면 글을 그대로 돌려준다(화면 트리가 전과 같다).
 */
export function withWrapPoints(text: string): ReactNode {
  const parts: ReactNode[] = [];
  let start = 0;
  for (const match of text.matchAll(/\S{21,}/g)) {
    const chunk = match[0];
    // 2 부터: 덩어리 첫 글자("/home" 의 /)만 줄 끝에 남기지 않는다.
    for (let i = 2; i < chunk.length; i++) {
      const prev = chunk[i - 1];
      const here = chunk[i];
      const afterSlash = prev === "/" && /[A-Za-z0-9._~-]/.test(here);
      const beforeDot =
        here === "." &&
        /[A-Za-z0-9]/.test(prev) &&
        /[A-Za-z]/.test(chunk[i + 1] ?? "");
      const beforeUpper = /[a-z]/.test(prev) && /[A-Z]/.test(here);
      const before = chunk[i - 2];
      const afterJoin =
        /[A-Za-z0-9]/.test(here) &&
        ((prev === ":" && before === ":") ||
          (prev === "_" && /[A-Za-z0-9]/.test(before)));
      if (afterSlash || beforeDot || beforeUpper || afterJoin) {
        const at = match.index + i;
        parts.push(text.slice(start, at), <wbr key={at} />);
        start = at;
      }
    }
  }
  if (parts.length === 0) return text;
  parts.push(text.slice(start));
  return parts;
}
