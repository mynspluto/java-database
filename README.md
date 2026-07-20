# java-database

키-값 DB(Redis 축소판)를 **바닥부터 직접** 만들며 Java 언어 + JVM/JDK 를 딥다이브하는 학습 프로젝트.
저장엔진 · 영속화(WAL) · 네트워크(raw TCP 서버·클라이언트) · 동시성 · 관측을 프레임워크 없이 손으로 구현한다.

- **구현 계획 + JVM/JDK 딥다이브 + 진행 표**: [`docs/PLAN.md`](docs/PLAN.md)

## 요구사항

- **JDK 21 이상** (LTS). 배포판은 무관 — Temurin·Corretto·MS 등 아무거나. 21 이 필요한 이유는 [PLAN 레이어 0](docs/PLAN.md).
- 빌드툴 없음. `javac`/`java` 만 사용.
- 선택: `/proc` 기반 OS 관측(레이어 5-C)과 컨테이너 실습은 **WSL2 + Docker** 필요. 나머지는 Windows/macOS/Linux 어디서든 됨.

```
java -version && javac -version    # 21+ 인지, 둘이 같은 버전인지 확인
```

## 빌드 · 실행

```
javac -d out src\Main.java     # 컴파일: .java -> .class
java  -cp out Main             # 실행
```

명령 각 토막의 의미·classpath·패키지 구조는 [`docs/toolchain.md`](docs/toolchain.md).
