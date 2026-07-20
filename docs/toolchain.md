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
| `Main` | 실행할 **클래스 이름**. 파일명 아님 — `Main.class` X, `out\Main` X, `.java` X. 그냥 클래스 이름 `Main` |

**흐름**: `java` → JVM 시작 → classpath(`out`)에서 `Main.class` 찾음 → `public static void main(String[])` 호출.

---

## 핵심 개념 4가지 (딥다이브)

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

#### package 는 "위치"가 아니라 "이름"이다

**패키지는 클래스 이름의 앞부분**이고, 클래스파일 **안에** 박힌다. `javap -v` 로 확인:

```
public class kvdb.Main
  this_class: #21     // kvdb/Main      ← 이름 자체에 패키지가 들어있음
```

폴더는 그 이름에서 **기계적으로 파생된 관습**일 뿐이다. 그래서 파일을 옮겨도 이름은 안 바뀐다.

#### `-d` 와 `package` 는 각자 다른 걸 정한다

> **출력 경로 = `<-d 값>` + `<패키지를 / 로 바꾼 것>` + `<클래스명>.class`**

| | 정하는 것 | 빼면 |
|---|---|---|
| **`-d out`** | **뿌리(base)** 를 어디로 | 소스 옆에 `.class` 가 떨어짐 |
| **`package kvdb;`** | 뿌리 **아래 상대경로** + **클래스 이름** | 뿌리 바로 아래로, 이름도 `Main` 이 됨 |

`package kvdb;` 인 채로 `-d` 없이 컴파일하면 `src\kvdb\Main.class` 로 가지만 **이름은 여전히 `kvdb.Main`** 이고 `java -cp src kvdb.Main` 으로 실행된다. → **위치는 정체가 아니라 "찾는 방법"**.

#### 인과 방향 — 무엇이 원인인가

| 무엇을 바꾸면 | 무엇이 바뀌나 |
|---|---|
| **`package` 선언** | 이름 · 출력경로 · 검색경로 · 접근경계 **전부** |
| 파일 위치(폴더 이동) | **아무것도 안 바뀜** |

**흔한 실수**: 파일만 `src\kvdb\` 로 옮기고 `package` 선언을 안 씀 → `javac` 는 조용히 통과하고 `out\Main.class`(기본 패키지)를 만든다. 그다음 `java -cp out kvdb.Main` 하면 `ClassNotFoundException`. **javac 은 소스가 어느 폴더에 있는지 신경쓰지 않는다.**

#### 바이트코드는 점이 아니라 `/` 를 쓴다

클래스파일 내부 표기(internal form)는 `kvdb/Main`, `java/lang/Object` 처럼 **슬래시**다. 소스는 점, 클래스파일은 슬래시.
→ `java` 런처가 `kvdb/Main` 도 받아주는 이유(내부에서 `/`→`.` 치환). **단 정식은 점 표기**이며, `import`·`Class.forName()` 은 치환이 없으므로 점을 습관으로 삼을 것.

#### `-cp` 에는 항상 **뿌리**를 준다

`out\kvdb\Main.class` 를 실행하려면 `-cp out` + `kvdb.Main`. `-cp out\kvdb` 를 주면 거기서 다시 `kvdb\Main.class` 를 찾으므로 실패.

#### 기본 패키지는 사실상 쓰지 말 것
JLS 상 **기본 패키지의 클래스는 다른 패키지에서 import 할 방법이 없다.** 패키지를 하나라도 만들면 나머지도 전부 패키지에 들어가야 한다.

### 4. import 는 "타입"을 가져온다 (패키지가 아님)

```java
import kvdb.store;           // 에러 — store 는 패키지지 클래스가 아님
import kvdb.store.Storage;   // 단일 타입 import (권장)
import kvdb.store.*;         // 온디맨드 import
```

**javac 은 마지막 마디를 항상 타입 이름으로 본다.** 그래서 `import kvdb.store;` 는 "`kvdb` 패키지의 `store` **클래스**"를 찾다 실패한다. 에러 메시지가 그대로 말해준다:

```
error: cannot find symbol
import kvdb.store;
           ^
  symbol:   class store        <- 클래스를 찾았다는 뜻
  location: package kvdb
```

- `*` 는 "패키지를 통째로 가져오기"가 아니라 **"그 패키지의 타입을 필요할 때 찾아라"**(on-demand). 하위 패키지는 포함 안 된다 — `java.util.*` 가 `java.util.concurrent` 를 포함하지 않음.
- **단일 타입 import 가 관례**: 어느 클래스가 어디서 왔는지 코드에 드러나고, 이름 충돌을 피한다(`java.util.List` vs `java.awt.List`).
- **import 는 런타임에 아무 일도 안 한다.** 컴파일러가 짧은 이름을 FQN 으로 풀어주는 **표기 편의**일 뿐 — 클래스파일에는 항상 FQN 이 박힌다(§3). "import 하면 로딩된다"는 오해.
- **같은 패키지 안**이면 import 불필요. `java.lang.*` 은 자동.

---

## 자주 만나는 에러

| 에러 | 원인 |
|---|---|
| `Could not find or load main class Main` | classpath(`-cp`) 틀림, 또는 클래스 이름/패키지 불일치 |
| `ClassNotFoundException: kvdb.Main` (폴더는 맞는데) | **파일만 옮기고 `package` 선언을 안 씀** → 기본 패키지로 컴파일됨(§3) |
| `-cp` 를 `out\kvdb` 로 줬는데 못 찾음 | `-cp` 는 **뿌리**를 준다. `-cp out` + `kvdb.Main` (§3) |
| `error: class Main is public, should be declared in a file named Main.java` | public 클래스명 ≠ 파일명 |
| `NoClassDefFoundError` (실행 중) | 컴파일은 됐는데 런타임 classpath 에 해당 클래스 없음 |
| `main method not found in class ...` | `public static void main(String[] args)` 시그니처 안 맞음 |
| `UnsupportedClassVersionError` | **`javac` 와 `java` 버전이 다름** — 새 JDK 로 컴파일하고 옛 JVM 으로 실행 |
| `cannot find symbol / symbol: class store` (import 줄) | **패키지를 import 함.** `import kvdb.store;` → `import kvdb.store.Storage;` (§4) |
| `cannot find symbol: class Storage` (다른 파일의 클래스) | **그 파일을 javac 에 안 넘김.** 소스 전부 넘기거나 `-sourcepath src` (아래 멀티 파일) |

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

## 멀티 파일 (파일이 둘 이상이 되는 순간부터)

```powershell
javac -d out (Get-ChildItem src -Recurse -Filter *.java).FullName   # PowerShell
java -cp out kvdb.Main
```

**파일 하나만 넘기면 다른 파일의 클래스를 못 찾는다.** `javac -d out src\kvdb\Main.java` 는 `Main` 이 쓰는 `kvdb.store.Storage` 를 어디서 찾을지 모른다 → `cannot find symbol`.

세 가지 해법:

| 방법 | 명령 | 평 |
|---|---|---|
| **소스 전부 넘기기** | 위 `Get-ChildItem` 형태 | **권장.** 파일이 늘어도 명령이 안 바뀜 |
| 손으로 나열 | `javac -d out A.java B.java` | 동작하지만 확장 불가. **순서는 무관** — javac 이 전부 읽고 심볼을 한 번에 해석 |
| `-sourcepath` | `javac -d out -sourcepath src src\kvdb\Main.java` | 의존 소스를 `src` 아래서 자동으로 찾아 같이 컴파일. 편하지만 **무엇이 컴파일됐는지 덜 명시적** |

> 이게 귀찮아지는 순간이 빌드툴(Gradle) 도입 시점. JVM 옵션(`-Xss`·`-Xmx`·NMT)까지 붙기 시작하면 특히.

**한 줄 스크립트로 줄이기** (`build.ps1`):
```powershell
javac -d out (Get-ChildItem src -Recurse -Filter *.java).FullName
```
→ `.\build.ps1` 후 `java -cp out kvdb.Main`.
