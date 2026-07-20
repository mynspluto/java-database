# javac / java — 컴파일·실행 명령 해부

## 이 프로젝트의 환경 (확정)

| 항목 | 값 |
|---|---|
| **JDK** | **Eclipse Temurin 21.0.11 LTS** (2026-07-20 확정) |
| `JAVA_HOME` | `C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot\` (Machine 범위) |
| 빌드 | 빌드툴 없이 `javac`/`java` 직접 (커지면 재검토) |
| OS | Windows 11 — `/proc` 계열 관측은 WSL2 필요([PLAN](PLAN.md) 레이어 5-C) |

**왜 21인가**: 레이어 4a의 **Virtual Thread(Loom)** 가 21에서 정식이다. 17이면 "가상 스레드는 스택마저 힙에 둔다"([memory-model](memory-model.md) §8·§9.5)는 핵심 대조 실습을 못 한다. 배포판(Temurin/Corretto/MS)은 같은 OpenJDK·HotSpot 소스라 **학습 목적에선 차이 없음** — 17부터 쓰던 Temurin 으로 일관성만 맞춤.

> 버전 확인: `java -version` · `javac -version` · `echo $env:JAVA_HOME`.
> 여러 JDK 가 깔려 있으면 **PATH 순서**가 승자를 정한다(Windows 는 Machine PATH → User PATH 순). `(Get-Command java).Source` 로 실제 해석 경로를 볼 것.

---

프로젝트 내내 반복할 두 줄. **컴파일(`javac`)과 실행(`java`)은 별개 단계**다.

```
javac -d out src\Main.java     # ① 소스(.java) → 바이트코드(.class)  [컴파일타임]
java  -cp out Main             # ② JVM 이 .class 를 로드해서 실행     [런타임]
```

---

## ① `javac -d out src\Main.java` — 컴파일

| 토막 | 의미 |
|---|---|
| `javac` | **Java 컴파일러**. `.java` 소스 → `.class` **바이트코드**로 번역. (기계어 아님!) |
| `-d out` | **d**estination — 결과 `.class` 를 `out\` 폴더에 넣어라. 없으면 `.java` 옆에 떨궈서 소스랑 뒤섞임 |
| `src\Main.java` | 컴파일할 소스 파일 |

**결과**: `out\Main.class` 생성. 이건 **바이트코드**지 CPU 가 직접 아는 기계어가 아냐 — JVM 이 읽는 중간 언어.

> `-d out` 을 쓰면 javac 이 **패키지 구조대로 하위 폴더를 자동 생성**해. 예: `package store;` 인 파일은 `out\store\KvStore.class` 로 감. (레이어 커지면 이게 편함)

---

## ② `java -cp out Main` — 실행

| 토막 | 의미 |
|---|---|
| `java` | **JVM 을 띄운다**. 지정한 클래스의 `main` 메서드를 찾아 실행 |
| `-cp out` | **c**lass**p**ath — "클래스(.class)를 `out\` 폴더에서 찾아라". JVM 이 클래스를 어디서 로드할지 알려주는 검색 경로 |
| `Main` | 실행할 **클래스 이름**. ⚠️ 파일명 아님 — `Main.class` X, `out\Main` X, `.java` X. 그냥 클래스 이름 `Main` |

**흐름**: `java` → JVM 시작 → classpath(`out`)에서 `Main.class` 찾음 → `public static void main(String[])` 호출.

---

## 핵심 개념 3가지 (딥다이브)

### 1. 바이트코드 = 플랫폼 독립
`.class` 는 특정 CPU/OS 용 기계어가 아니라 **JVM 이 해석하는 바이트코드**. 그래서 같은 `.class` 가 Windows·Linux·Mac 어디서든 돎("write once, run anywhere"). JVM 이 실행 중 자주 쓰는 코드를 **JIT** 로 기계어로 바꿔 최적화. → `java --version` 의 `mixed mode` 가 이 뜻(인터프리터 + JIT 혼용).

### 2. classpath = JVM 의 클래스 검색 경로
JVM 은 클래스를 로드할 때 classpath 를 뒤져. `-cp out` 을 빼먹으면 현재 폴더(`.`)만 봐서 `Main.class` 를 못 찾음:
```
Error: Could not find or load main class Main   ← classpath 문제 1순위 증상
```
- 여러 경로: `java -cp out;lib\junit.jar Main` (Windows 구분자 `;`, Linux/Mac 은 `:`)
- 나중에 외부 jar(테스트 등) 붙일 때 여기에 추가.

### 3. 패키지 → 폴더 → 정규 이름(FQN)
`package store;` 인 `KvStore` 는:
- 소스: `src\store\KvStore.java`
- 클래스파일: `out\store\KvStore.class`
- 실행: `java -cp out store.KvStore`  ← **점 표기 정규 이름**(FQN), 폴더 구분자 아님

---

## 자주 만나는 에러

| 에러 | 원인 |
|---|---|
| `Could not find or load main class Main` | classpath(`-cp`) 틀림, 또는 클래스 이름/패키지 불일치 |
| `error: class Main is public, should be declared in a file named Main.java` | public 클래스명 ≠ 파일명 |
| `NoClassDefFoundError` (실행 중) | 컴파일은 됐는데 런타임 classpath 에 해당 클래스 없음 |
| `main method not found in class ...` | `public static void main(String[] args)` 시그니처 안 맞음 |

---

## 단축: 컴파일 없이 한 방 (Java 11+)
단일 파일은 `.class` 안 만들고 바로 실행 가능(내부적으로 메모리에서 컴파일):
```
java src\Main.java
```
> 편의용. 여러 파일·패키지 쓰면 결국 `javac`/`java` 2단계로 돌아옴. 학습 초반엔 **2단계를 눈으로 보는 게** classpath·바이트코드 개념 체득에 좋음.

## 멀티 파일 (레이어 커지면)
```
javac -d out (Get-ChildItem src -Recurse -Filter *.java).FullName   # PowerShell
java -cp out Main
```
파일 많아지고 이게 귀찮아지는 순간이 빌드툴(Gradle) 도입 시점.
