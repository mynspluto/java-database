# 키-값 DB 구현 계획 — JVM/JDK 딥다이브 트랙

> 사용자가 **직접 손으로** 코드를 쓴다. 이 문서는 *무엇을·어떤 순서로·무엇을 알아야 하는지*의 지도일 뿐, 정답 코드는 없다.
> 각 레이어는 **자체로 동작**한다(중간에 멈춰도 완결). 만들고 → 표준(Redis/RocksDB/`java.util`)과 비교 → "왜 저게 나은가" 분석 → 리팩터링.
> 딥다이브 대상: **언어(Java) + JVM 메모리/GC/JMM + JDK 관측 도구 + OS/네트워크 경계**.

---

## 레이어 0 — 프로젝트 셋업 (사용자 결정)
- **빌드**: 단순 `javac`/`java` 로 시작 → 커지면 빌드툴 검토. (프레임워크 X, 표준 JDK 만)
- **JDK 버전**: LTS(21) 권장 — virtual thread(Loom)·`java.lang.foreign`(Panama) 등 딥다이브 소재가 최신에 있음.
- **패키지 구조 감**: `store`(엔진) / `wal`(영속화) / `net`(프로토콜·서버) / `concurrent`(락·풀) / `index` / `metrics`. 구조도 직접 정하는 게 학습.

**알아야 할 것**: `javac`/`java` 동작·classpath → **[`docs/toolchain.md`](toolchain.md)**, `-Xms/-Xmx/-Xss` 등 JVM 실행 옵션 → **[`docs/jvm-options.md`](jvm-options.md)**, `public static void main` 진입점, JAR 패키징.

---

## 레이어 1 — 단일스레드 인메모리 (get / set / del)

**만드는 것**: 문자열 key→value 저장. 명령 루프(REPL) 하나. 자료구조는 직접(HashMap 축소판) 짜보거나 `HashMap` 쓰고 나중에 비교.

**딥다이브 포인트**
- **해시맵 내부**: 버킷·체이닝·로드팩터·리사이징(amortized O(1)). 직접 짠 것 vs `java.util.HashMap`(트리화 threshold 8, `hash()` 스프레딩) 비교.
- **`equals`/`hashCode` 계약** — 안 지키면 조회 실패. 불변 key 의 중요성.
- **힙에 뭐가 쌓이나**: 모든 `String`·`Node` 객체가 힙. `new` 마다 할당. (메모리 맵: [jvm-options.md](jvm-options.md) §메모리 맵)
- **String 내부**: `char[]`→(Java 9+) `byte[]` + coder, String pool, `intern()`. key 를 pool 에 넣을지 trade-off.

**JVM 관측 실습**: `jps` 로 PID → `jmap -histo <pid>` 로 어떤 객체가 몇 개 쌓였는지. 대량 put 후 힙 증가를 `jstat -gc <pid> 1000` 로 관찰.

**비교 질문**: 왜 `HashMap` 은 로드팩터 0.75 인가? 왜 리사이징이 2배인가?

---

## 레이어 2 — 영속화 (WAL / 스냅샷 / 복구)

**만드는 것**: 쓰기를 append-only 로그(WAL)에 먼저 기록 → 재시작 시 재생(replay)으로 복구. 주기적 스냅샷으로 로그 압축.

**딥다이브 포인트**
- **파일 I/O**: `FileOutputStream` vs `FileChannel`. `flush()` ≠ 디스크 도달 — **`fsync`(`FileDescriptor.sync()` / `FileChannel.force(true)`)** 안 하면 OS page cache 에만 있고 크래시 시 유실. 이게 durability 의 핵심.
- **버퍼링**: `BufferedOutputStream`, write syscall 횟수 vs 지연. 힙 버퍼 vs `ByteBuffer.allocateDirect()`(off-heap, [jvm-options.md](jvm-options.md) §다이렉트 메모리).
- **직렬화 포맷**: 길이-프리픽스 바이너리 직접 설계. `DataOutputStream`(빅엔디안) / `ByteBuffer`. Java `Serializable` 은 **왜 피하나**(버전·보안·크기).
- **크래시 복구**: 반쯤 쓰인 마지막 레코드 감지(체크섬/길이검증). WAL replay 멱등성.
- **파일락**: `FileChannel.lock()` 으로 이중 기동 방지.

**JVM/OS 관측**: `jcmd <pid> VM.native_memory summary`(NMT) 로 direct buffer 추적. 다이렉트 버퍼 안 풀면 누수 → NMT 로 확인. `strace`(리눅스)/procmon 으로 실제 `write`/`fsync` syscall 관찰.

**비교**: Redis RDB(스냅샷) vs AOF(로그) — 내가 만든 게 어느 쪽? RocksDB WAL. (DDIA 3장 "로그 구조 저장소")

---

## 레이어 3 — 네트워크: 서버 ↔ 클라이언트 (소켓, 단일 연결)

> **여기가 "로우한 부분" 핵심.** 서버와 클라이언트를 **둘 다 직접**. HTTP·프레임워크 없이 raw TCP.

**만드는 것**: `ServerSocket` 으로 리슨 → 연결 수락 → 요청 바이트 파싱 → 명령 실행 → 응답 바이트. 클라이언트도 `Socket` 으로 직접 구현. 텍스트 프로토콜(RESP 유사) 직접 설계.

**딥다이브 포인트**
- **TCP 기초**: 3-way handshake, 스트림(경계 없음!) → **프레이밍 직접**(길이 프리픽스 or 구분자). "한 번 read = 한 메시지" 착각이 최대 함정.
- **블로킹 I/O 모델**: `accept()`/`read()` 가 블록. `InputStream`/`OutputStream` ↔ 커널 소켓 버퍼([jvm-options.md](jvm-options.md) §메모리 맵 — OS 커널 영역).
- **`read()` 반환값**: -1(EOF), 0, n — 부분 읽기 루프 필수. `readFully` 를 왜 직접 짜야 하나.
- **Nagle/TCP_NODELAY**, `SO_KEEPALIVE`, `SO_REUSEADDR` — `setTcpNoDelay` 등 소켓 옵션의 의미.
- **바이트 ↔ 문자**: 인코딩(UTF-8) 명시 안 하면 플랫폼 의존 버그.
- **자원 정리**: try-with-resources, half-close, `SocketException: Connection reset` 의 의미.

**JVM 관측**: `jstack <pid>` 로 `accept()`/`read()` 에 블록된 스레드 확인. `netstat`/`ss` 로 소켓 상태(ESTABLISHED/TIME_WAIT).

**비교**: RESP 프로토콜 설계 이유(단순·파싱 빠름). 왜 텍스트인가 vs 바이너리.

---

## 레이어 4 — 병렬처리 (동시성 학습 정점 · 둘 다 만들어 비교)

### 4a. 스레드 기반 (먼저)
**만드는 것**: 연결마다 스레드(or 스레드풀). 공유 저장소 동시 접근 보호.

**딥다이브 포인트**
- **JMM(Java Memory Model)**: happens-before, `volatile`(가시성), `synchronized`(가시성+원자성). **왜 `volatile` 만으로 count++ 안전 X**(read-modify-write).
- **락**: `synchronized` vs `ReentrantLock`(tryLock·공정성), `ReadWriteLock`(읽기 많은 KV 에 적합?), 락 세분화(전역락 → 버킷/샤드락).
- **동시 자료구조**: 직접 락 vs `ConcurrentHashMap`(세그먼트/CAS·`compute`). 만든 뒤 비교.
- **race condition·데드락**을 **의도적으로 재현** → 진단. lost update, check-then-act.
- **스레드풀**: `ThreadPoolExecutor` 파라미터(core/max/queue/reject), 스레드당 스택(`-Xss`) → **스레드 폭발**(수천 연결 시 OOM/컨텍스트스위칭). 이 한계를 **몸으로 겪는 게 4b 동기**.
- **원자성 도구**: `AtomicLong`, CAS, ABA 문제.
- **(욕심) Virtual Threads(Loom, JDK21)**: 스레드-per-연결을 싸게 — 캐리어 스레드·pinning. "왜 이게 게임체인저인가".

**JVM 관측**: `jstack <pid>` → **데드락 자동 감지**("Found one Java-level deadlock"). `jstat -gc` 로 스레드 폭발 시 힙/GC. JFR 로 락 경합(monitor blocked) 프로파일.

### 4b. 이벤트 루프 (나중) — NIO Selector, 논블로킹
**만드는 것**: 단일(or 소수) 스레드 + `Selector` 로 다중 연결 다중화. 논블로킹 `SocketChannel`.

**딥다이브 포인트**
- **`Selector`/`SelectionKey`**(OP_ACCEPT/READ/WRITE), 논블로킹 `read()` 반환 0 처리, 부분 write 시 OP_WRITE 등록.
- **`ByteBuffer` 정복**: position/limit/capacity, `flip()`/`compact()`/`clear()` — 최대 실수 지점.
- **다이렉트 버퍼 + zero-copy**(`FileChannel.transferTo`), off-heap 관리([jvm-options.md](jvm-options.md)).
- epoll/kqueue 를 JVM 이 어떻게 감싸나(리액터 패턴). Netty 가 감춘 것.
- **왜 단일스레드로 수만 연결**(Redis/Node 원리) — 4a 스레드폭발 겪은 뒤 체득.

**JVM 관측**: `jstack` 로 이벤트루프 1개가 다 처리하는지. JFR 로 CPU·할당률. 4a vs 4b 부하 벤치(연결 수 ↑) 비교표.

**비교**: 스레드 모델(Tomcat) vs 이벤트루프(Redis/Node/Netty) trade-off. C10k 문제.

---

## 레이어 5 — 모니터링 (관측 가능성)

**만드는 것**: 앱 메트릭 수집(QPS·히트율·명령별 지연·p99·슬로우로그) + `INFO`/`STATS` 명령으로 노출.

**딥다이브 포인트**
- **지연 측정**: `System.nanoTime()`(monotonic) vs `currentTimeMillis`. p99 계산(히스토그램·HdrHistogram 개념, 직접 버킷).
- **메트릭 동시성**: 카운터를 `LongAdder` vs `AtomicLong`(경합 시 차이).
- **슬로우로그**: 임계 초과 명령 링버퍼 저장.
- **(A) 앱 메트릭** = 직접(CloudWatch 커스텀 개념) / **(B) JVM 관측** = JDK 공짜.

**JVM 관측 도구 정복** (실행 옵션은 [jvm-options.md](jvm-options.md) §진단·관측 옵션)
- `jps` PID · `jstat -gc` GC/힙 추이 · `jstack` 스레드/데드락 · `jmap -histo`/`-dump` 힙·누수(이펙티브자바 item7) · `jcmd`(만능: NMT·JFR 제어) · `jconsole`/VisualVM GUI · **JFR**(Flight Recorder — 저오버헤드 프로파일: 할당·락·IO) → JMC 로 분석.
- 실습: 레이어 2~4 에서 **내가 심은 누수/데드락/할당폭증**을 이 도구로 진단 = 실전 디버깅.

---

## 레이어 6 (욕심) — 인덱스 / 복제

- **인덱스**: **Skip List**(쉬움 — Redis ZSet 실제 구현) → **B-tree / LSM**(어려움). 범위 검색, 읽기/쓰기 증폭 trade-off. (DDIA 3장)
- **복제**: WAL 스트리밍(레이어 2 재활용) → 복제 지연·일관성. (DDIA 5장)
- **딥다이브**: 캐시라인·false sharing, GC 튜닝(G1 vs ZGC — LSM compaction 시 할당폭증 대응).

---

## 진행 표기 & 회고
- ⬜ todo / 🟦 진행 / ✅ 완료. 완료 시: **회고 1줄 + 표준(Redis/RocksDB/`java.util`) 비교 링크**.
- 각 레이어 끝에 "만든 것 vs 표준: 무엇이 다르고 왜 저게 나은가" 1문단.

| 레이어 | 상태 | 회고 |
|---|---|---|
| 0 셋업 | ⬜ | |
| 1 인메모리 | ⬜ | |
| 2 영속화 | ⬜ | |
| 3 네트워크 | ⬜ | |
| 4a 스레드 | ⬜ | |
| 4b 이벤트루프 | ⬜ | |
| 5 모니터링 | ⬜ | |
| 6 인덱스/복제 | ⬜ | |

---

## 면접 시그널 (부산물)
- "프레임워크가 감춘 것" 직접 마주: 소켓·프레이밍·JMM·GC·NIO.
- 동시성: JMM/락/데드락 재현·진단, 스레드 vs 이벤트루프 trade-off 체득.
- 관측: 내가 심은 버그를 JDK 도구로 잡은 실전 스토리.
- 저장엔진: WAL·fsync·durability, LSM vs B-tree (DDIA 인용).
