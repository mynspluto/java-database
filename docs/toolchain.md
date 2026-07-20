# javac / java — 컴파일·실행 명령 해부

프로젝트 내내 반복할 두 줄. **컴파일(`javac`)과 실행(`java`)은 별개 단계**다.

> 필요 버전과 빌드 방식은 [README](../README.md), 그 **선택 근거**는 [PLAN 레이어 0](PLAN.md) 참조.

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
| `UnsupportedClassVersionError` | **`javac` 와 `java` 버전이 다름** — 새 JDK 로 컴파일하고 옛 JVM 으로 실행 |

### JDK 가 여러 개 깔렸을 때 (PC 옮겨 다니면 자주 만남)

- **`javac` 와 `java` 가 서로 다른 JDK 를 가리킬 수 있다** → 위 `UnsupportedClassVersionError` 의 정체. 둘 다 확인할 것: `java -version` · `javac -version`.
- 승자는 **PATH 순서**가 정한다. Windows 는 **Machine PATH 를 먼저, User PATH 를 뒤에** 이어 붙이므로 User 쪽에 새 JDK 를 넣어도 Machine 쪽 옛 JDK 가 이긴다.
- 실제 해석 경로 보기: `(Get-Command java).Source` (PowerShell) / `which -a java` (bash).
- `JAVA_HOME` 은 **IDE·빌드툴이 보는 값**이고 터미널의 `java` 는 **PATH** 를 본다 → 둘이 어긋나면 "IDE 에선 되는데 터미널에선 안 됨"이 발생.

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
