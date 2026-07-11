# JVM 실행 옵션 (`-Xms`, `-Xmx`, `-Xss`, `-XX:*`)

> **컴파일이 아니라 실행 옵션.** `java` 에만 붙인다 (`javac` 아님). `.class` 를 어떻게 **실행/튜닝**할지 JVM 에 지시.
> ```
> java -Xms256m -Xmx256m -Xss1m -XX:+UseG1GC -cp out Main
> ```
> 이 프로젝트에서 "내가 심은 누수/데드락/할당폭증"을 재현·관측할 때 이 옵션들로 조건을 만든다.

옵션 문법 3종:
- `-X...` = 표준화된 비표준 옵션 (Xms/Xmx/Xss). 대부분 JVM 공통.
- `-XX:+Flag` / `-XX:-Flag` = 켜기(+)/끄기(-) 불리언.
- `-XX:Key=Value` = 값 지정 (예: `-XX:MaxMetaspaceSize=128m`).

단위: `k`/`m`/`g` (예: `512m`, `2g`).

---

## 1. 힙 크기 — `-Xms` / `-Xmx` ★ 제일 많이 씀

| 옵션 | 뜻 | 기본값 |
|---|---|---|
| `-Xms<size>` | 힙 **초기(시작)** 크기 | 물리메모리 비율 (보통 1/64) |
| `-Xmx<size>` | 힙 **최대** 크기 | 물리메모리 1/4 |

- **힙** = `new` 로 만든 모든 객체가 사는 곳, GC 대상. 우리 KV 저장소(HashMap·String·Node)가 다 여기.
- 힙이 `-Xmx` 까지 다 차고 GC 로도 못 비우면 → **`OutOfMemoryError: Java heap space`**.
- **`-Xms` == `-Xmx` 로 같게 주는 이유**: 실행 중 힙을 늘렸다 줄였다(리사이즈) 하는 비용·지연을 없앰. 서버(우리 DB)는 보통 고정.

**이 프로젝트 활용**:
- 레이어 1: 힙 작게(`-Xmx64m`) 주고 대량 `SET` → **일부러 OOM 내보고** `jmap -histo` 로 뭐가 쌓였나 관측.
- 레이어 5~6: GC 튜닝 실험 기준선.

## 2. 스레드 스택 — `-Xss` ★ 레이어 4 직결

- **스레드마다** 별도 스택(로컬 변수·메서드 프레임). `-Xss` 는 **스택 1개 크기**(기본 ~512k~1m).
- 재귀 너무 깊으면 → **`StackOverflowError`** (스택 넘침).
- **스레드가 많으면**: 스레드 수 × `-Xss` = 네이티브 메모리 소모. 레이어 4a 에서 **연결마다 스레드** 만들다 수천 개 → 스택 메모리 폭발 = **스레드-per-연결의 한계**. `-Xss` 를 줄이면 더 버티지만 깊은 재귀 위험 ↑. 이 trade-off 를 몸으로 겪는 게 4b(이벤트루프) 동기.

## 3. 그 외 메모리 영역 옵션

| 옵션 | 영역 | 이 프로젝트에서 |
|---|---|---|
| `-XX:MaxMetaspaceSize=<size>` | **메타스페이스**(클래스 메타데이터, 네이티브 메모리) | 리플렉션·클래스 많이 만들면 관찰. 보통 기본값 OK |
| `-XX:MaxDirectMemorySize=<size>` | **다이렉트 메모리**(off-heap, `ByteBuffer.allocateDirect`) | 레이어 2 WAL 버퍼 / 4b NIO 버퍼. **안 풀면 누수** → 여기서 상한 걸고 재현 |
| `-XX:ReservedCodeCacheSize=<size>` | **Code Cache**(JIT 이 만든 기계어) | JIT 딥다이브 시. `mixed mode` 의 기계어가 여기 캐싱 |

> 메모리 영역 5종(힙/스택/메타스페이스/다이렉트/코드캐시)의 전체 지도는 이 문서 하단 "메모리 맵" 참고.

## 4. GC 선택 — `-XX:+Use___GC` (레이어 5~6)

| 옵션 | GC | 특징 |
|---|---|---|
| `-XX:+UseG1GC` | G1 (기본, JDK 9+) | 균형형. 우리 기본값 |
| `-XX:+UseZGC` | ZGC | 초저지연(무정지 지향). 큰 힙·p99 민감할 때 |
| `-XX:+UseParallelGC` | Parallel | 처리량 우선, 지연 큼 |
| `-XX:+UseSerialGC` | Serial | 단일스레드, 작은 힙/학습용 |

레이어 5~6 에서 **같은 부하를 GC 만 바꿔** p99·정지시간 비교 = DDIA 관측 트랙.

## 5. 진단·관측 옵션 (레이어 5 관측 때 자주)

| 옵션 | 효과 |
|---|---|
| `-XX:+HeapDumpOnOutOfMemoryError` | OOM 나는 순간 힙덤프(`.hprof`) 자동 저장 → 누수 부검 |
| `-XX:HeapDumpPath=<dir>` | 위 덤프 저장 위치 |
| `-Xlog:gc*` | GC 로그 상세 출력 (JDK 9+ 통합 로깅). 언제 얼마나 멈추나 |
| `-XX:+PrintCompilation` | JIT 이 어떤 메서드를 기계어化하는지 로그 |
| `-XX:StartFlightRecording=duration=60s,filename=rec.jfr` | **JFR** 시작 — 저오버헤드로 할당·락·IO 프로파일 → JMC 로 분석 |
| `-XX:NativeMemoryTracking=summary` | **NMT** — off-heap/다이렉트 메모리 추적 (`jcmd <pid> VM.native_memory`) |

---

## 메모리 맵 (옵션이 어느 영역을 건드리나)

```
┌──────────────────────── JVM 프로세스 메모리 ────────────────────────┐
│ 힙 (Heap)              객체 인스턴스, GC 대상        ← -Xms / -Xmx    │
│ 스택 (Stack, 스레드별)  로컬변수·프레임, 자동해제      ← -Xss           │
│ 메타스페이스            클래스 메타데이터 (네이티브)   ← MaxMetaspaceSize│
│ 다이렉트 메모리(Off-Heap) NIO 버퍼, 수동관리 ⚠️        ← MaxDirectMemorySize│
│ 코드 캐시               JIT 기계어                    ← ReservedCodeCacheSize│
└────────────────────────────────────────────────────────────────────┘
                              ↓
                      OS 커널: 소켓 버퍼(TCP) 등
```

| 영역 | 할당 | 해제 | 누수 위험 |
|---|---|---|---|
| 힙 | `new` | GC | 낮음(단, 참조 유지 시 논리적 누수 — item7) |
| 스택 | 자동 | 메서드 종료 | 없음 (단 스레드 과다 = 총량 폭발) |
| 메타스페이스 | 자동 | 클래스 언로드 | 낮음 |
| **다이렉트/네이티브** | 명시적 | **수동** | ⚠️ 높음 → NMT 로 추적 |

---

## 확인 명령
```
java -XX:+PrintFlagsFinal -version | findstr /I "HeapSize ThreadStackSize"   # 현재 유효 기본값 덤프
java -Xms256m -Xmx256m -Xss1m -XX:+UseG1GC -cp out Main                       # 옵션 적용 실행
```
> 힌트: 옵션은 **클래스 이름 앞**에 온다. `java [옵션들] -cp out Main`. Main 뒤에 오는 건 프로그램 인자(`args`)로 넘어가지 JVM 옵션이 아님.
