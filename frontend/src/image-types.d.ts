// 그림 파일을 import 할 때(start/logo.webp) 쓰는 타입. next-env.d.ts 에도 같은 줄이
// 있지만 그 파일은 git 에 없고 빌드 때 생긴다. CI 는 빌드 전에 타입 검사를 먼저
// 돌리므로 여기 없으면 TS2307 로 멈춘다.
/// <reference types="next/image-types/global" />
