# 키-값 DB 구현 계획 — JVM/JDK 딥다이브 트랙

> 사용자가 **직접 손으로** 코드를 쓴다. 이 문서는 *무엇을·어떤 순서로·무엇을 알아야 하는지*의 지도일 뿐, 정답 코드는 없다.
> 각 레이어는 **자체로 동작**한다(중간에 멈춰도 완결). 만들고 → 표준(Redis/RocksDB/`java.util`)과 비교 → "왜 저게 나은가" 분석 → 리팩터링.
> 딥다이브 대상: **언어(Java) + JVM 메모리/GC/JMM + JDK 관측 도구 + OS/네트워크 경계**.

---

## 레이어 0 — 프로젝트 셋업 (사용자 결정)
- **빌드**: 단순 `javac`/`java` 로 시작 → 커지면 빌드툴 검토. (프레임워크 X, 표준 JDK 만)
- **JDK 버전**: LTS(21) 권장 — virtual thread(Loom)·`java.lang.foreign`(Panama) 등 딥다이브 소재가 최신에 있음.
- **패키지 구조 감**: `store`(엔진) / `wal`(영속화) / `net`(프로토콜·서버) / `concurrent`(락·풀) / `index` / `metrics`. 구조도 직접 정하는 게 학습.

**알아야 할 것**: `javac`/`java` 동작·classpath → **[`docs/toolchain.md`](toolchain.md)**, `-Xms/-Xmx/-Xss` 등 JVM 실행 옵션 → **[`docs/jvm-options.md`](jvm-options.md)**, 스택·힙 원리(수명·프레임·SOE/OOM·할당 syscall·CPU/OS/JVM 층위) → **[`docs/memory-model.md`](memory-model.md)**, `public static void main` 진입점, JAR 패키징.

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

### 관측 3층 — 층마다 보이는 것이 다르다

원리는 [`memory-model.md`](memory-model.md) **§9.5(좌우 대조)·§9.6(RSS ≠ 힙)**. 핵심: **한 프로세스의 같은 메모리를 세 층이 각각 다르게 본다. 한 층만 보면 반드시 놓친다.**

| 층 | 무엇을 보나 | 누가 만드나 | 대표 도구 | 성격 |
|---|---|---|---|---|
| **A. 앱** | QPS·히트율·p99·슬로우로그 | **내가 직접 구현** | `INFO`/`STATS` 명령 | **상시 수집** |
| **B. JVM** | 힙 속 객체·GC·스레드·JVM 영역별 사용량 | JDK 공짜 | `jstat`·`jstack`·`jmap`·`jcmd`(NMT)·JFR | 필요 시 붙임 |
| **C. OS** | VMA 배치·RSS·스왑·프로세스 생사 | 커널 공짜 | `maps`·`smaps`·`pmap`·`top`·`dmesg` | **부검·교차확인** |

- **A는 "내 DB가 잘 도나"(제품 지표), C는 "이 프로세스가 왜 죽었나"(부검).** 목적이 다르니 둘 다 필요하다.
- **B의 NMT가 유일하게 경계에 걸친 번역기** — 커널이 준 익명 영역을 JVM 의미(Java Heap/Thread/Code/Class)로 쪼개 준다. **B와 C를 잇는 다리.**

### 5-A. 앱 메트릭 — 직접 구현

**딥다이브 포인트**
- **지연 측정**: `System.nanoTime()`(monotonic) vs `currentTimeMillis`. p99 계산(히스토그램·HdrHistogram 개념, 직접 버킷).
- **메트릭 동시성**: 카운터를 `LongAdder` vs `AtomicLong`(경합 시 차이).
- **슬로우로그**: 임계 초과 명령 링버퍼 저장.
- 개념 연결: CloudWatch 커스텀 메트릭 = 이걸 밖으로 내보낸 것.

### 5-B. JVM 레벨 관측 (실행 옵션은 [jvm-options.md](jvm-options.md) §진단·관측 옵션)

| 도구 | 보는 것 | 이 프로젝트에서 |
|---|---|---|
| `jps` | PID | 시작점 |
| `jstat -gc <pid> 1000` | GC 횟수·힙 세대별 추이 | 레이어 1 대량 put 시 힙 증가 |
| `jstack` | 스레드 덤프·**데드락 자동 감지** | **레이어 4a** 락 버그 |
| `jmap -histo` / `-dump` | 클래스별 객체 수 / 힙덤프 | 캐시 누수(이펙티브자바 item7) |
| **`jcmd <pid> VM.native_memory summary`** | **NMT — 영역별 reserved/committed** | **힙 밖 누수**(스레드·direct) |
| JFR + JMC | 저오버헤드 프로파일(할당·락·IO) | 4a vs 4b 비교 |

- **NMT는 `-XX:NativeMemoryTracking=summary` 로 켜고 시작해야** 잡힌다(기본 꺼짐).
- **reserved vs committed** = 예약한 가상 주소 vs 실제 커밋. `mmap` 은 주소만 예약하고 물리 페이지는 touch 때 붙기 때문(memory-model §6).

### 5-C. OS 레벨 관측

| 도구 | 보는 것 | 주의 |
|---|---|---|
| `cat /proc/<pid>/maps` | **VMA 배치도** — 권한·이름·익명 여부 | **사용량 아님.** 크기도 주소 빼서 계산 |
| `cat /proc/<pid>/smaps` | maps + 영역별 `Rss`·`Swap`·`Pss` | **진짜 사용량은 여기** |
| `pmap -x <pid>` | 위 둘을 표로 정리 | 빠르게 볼 때 |
| `top` / `/proc/<pid>/status` | 프로세스 총계(`VmRSS`, `VmSize`) | 총계만 |
| `dmesg` / `journalctl` | **OOM Killer 흔적** | `Killed process` — 스택트레이스 없이 죽었을 때 |
| `/proc/meminfo`·`free -h` | **시스템 전체** | maps는 프로세스 하나짜리 |

- **maps = 도면 / smaps = 사용량.** 이 구분을 놓치면 `-Xmx16g` 짜리 VSZ를 보고 "16GB 쓴다"고 오진한다. (약어 VSZ/RSS/PSS 정의는 memory-model §9.4)

**RSS 관측 — 실전 4단계** (묻는 게 달라지면 명령도 달라진다)

| 묻는 것 | 명령 | 읽는 법 |
|---|---|---|
| 1. **지금 얼마 쓰나** | `grep VmRSS /proc/<pid>/status`<br>또는 `ps -o pid,rss,vsz -p <pid>` | `top` 의 `RES` 열과 같은 값 |
| 2. **뭐가 먹나** | `pmap -x <pid> \| sort -k3 -n \| tail -20` | 3번째 열이 RSS. **큰 덩어리 1개=힙 / `-Xss` 크기 조각 수백 개=스레드 스택** |
| 3. **왜 먹나** | **`jcmd <pid> VM.native_memory summary`** | Java Heap 이 작은데 RSS 크면 → **Thread·Code·Internal** 항목 확인 |
| 4. **누수인가** | RSS 를 주기적으로 파일에 로깅 → 기울기 | **절대값 아니라 기울기.** 부하 멈춰도 안 내려오면 누수 |

- 총계만 정확히: **`cat /proc/<pid>/smaps_rollup`** (`Rss`·`Pss`·`Swap` 합계 한 번에, 커널 4.14+).
- **3번이 핵심**: RSS 만 보면 "크다"까지고 **왜 큰지는 NMT 가 답한다.** NMT 안 켜두면 관측이 반쪽 → `-XX:NativeMemoryTracking=summary` 를 기동 옵션에 상시 포함.

**윈도우 대응** (`/proc` 없음 — maps·smaps·pmap 은 리눅스 전용)

| Windows | Linux 대응 | 비고 |
|---|---|---|
| `Get-Process -Id <pid> \| Select WorkingSet64` | **RSS** | 작업관리자 → 세부정보 → 열 추가 **"작업 집합"** |
| Private Bytes | ≈ 사설 커밋(PSS 개념에 가까움) | 기본 "메모리" 열은 Private Working Set |
| **VMMap** (Sysinternals) | `pmap -x` | 영역별 분해 |
| 성능 모니터(PerfMon) | RSS 시계열 로깅 | 4번 추이용 |

→ **1·2·4번은 WSL2 권장, 3번(`jcmd`·NMT)은 윈도우에서 그대로 된다.** A·B층 전체가 윈도우에서 완주 가능하고 **C층만 WSL이 필요**.

**컨테이너/AWS에서 볼 때**

| 명령 | 주의 |
|---|---|
| `cat /sys/fs/cgroup/memory.current` | **순수 RSS 아님** — 페이지 캐시 포함. 레이어 2 WAL 쓰기 시작하면 부풀어 보인다 |
| `cat /sys/fs/cgroup/memory.stat` | `anon`(≈RSS) 과 `file`(페이지 캐시)을 **분리해서** 볼 것 |
| `docker stats` | MEM USAGE / LIMIT |
| CloudWatch Container Insights | Fargate 에서 셸 없이 볼 때 |

### 관통 실습 — 같은 현상을 3층에서 보기

이 레이어의 진짜 목표. **각 실습은 "한 층만 보면 왜 오진하는가"를 체험하는 것.**

| # | 실습 | A(앱) | B(JVM) | C(OS) | 배우는 것 |
|---|---|---|---|---|---|
| 1 | **RSS ≠ 힙**: `-Xmx512m` 로 띄우고 **레이어 4a 스레드 200개** 연결 | QPS 정상 | `jmap -histo` **깨끗** / NMT **Thread 급증** | `smaps` **RSS 폭증** | **힙 도구로 안 잡히는 죽음**(memory-model §9.6) |
| 2 | **reserve ≠ 커밋**: `-Xmx4g` 로 띄우고 시작 직후 관찰 → `-XX:+AlwaysPreTouch` 로 재실행 비교 | — | NMT reserved 4G vs committed 소량 | `maps` Size 4G vs `smaps` Rss 소량 | **가상 예약과 물리 배정은 다르다** |
| 3 | **OOM Killer**: `docker run -m 512m` + `-Xmx512m` 으로 띄워 죽여보기 | 로그 뚝 끊김 | **아무 에러 없음**(JVM 증발) | `dmesg` 에 `Killed process`, **exit 137** | **커널이 죽이면 Java 에러가 없다**(§5) |
| 4 | **누수 잡기**: 레이어 1~2에 캐시 누수 심고 방치 | 히트율·p99 악화 | `jstat` GC 빈발 / `jmap -histo` 범인 클래스 | RSS 우상향 | 힙 누수는 **B가 정답** |
| 5 | **direct 버퍼 누수**: 레이어 2/4b NIO 버퍼 안 풀기 | — | `jmap` 깨끗 / **NMT Internal 증가** | RSS 우상향 | off-heap은 **NMT만 본다** |

**진단 순서 습관화**: A(증상 감지) → B(`jmap` 힙 확인 → 깨끗하면 **NMT**) → C(교차 확인·부검). **1·5번이 "B의 힙 도구만 믿으면 실패"하는 대표 사례.**

**전제 도구**: 1·2·4·5번은 JDK만 있으면 된다(윈도우 가능, `/proc` 볼 땐 WSL2). **3번은 Docker 필요** — `-m` 으로 메모리 리밋을 걸어야 재현된다.

> **3번은 Fargate 리허설이다.** 컨테이너 리밋 초과로 죽는 경로가 배포 환경과 **동일**하고, 흔적 찾는 곳만 `dmesg` → `stoppedReason` 으로 바뀔 뿐(아래 배포 절). 로컬에서 한 번 겪어두면 `-Xmx` 를 태스크 메모리와 같게 주는 실수를 안 한다.
> 확인할 것: `docker inspect <id> --format '{{.State.ExitCode}} {{.State.OOMKilled}}'` → **`137 true`**.

### 배포하면 달라지는 것 (EC2 vs Fargate)

로컬은 3층이 다 열려 있지만 **배포 환경은 층을 뺏어간다.** 그래서 A층(앱이 스스로 말하는 지표)을 직접 만드는 값어치가 여기서 드러난다.

| 층 | EC2 | Fargate |
|---|---|---|
| **A. 앱** | 그대로 (CloudWatch 커스텀 메트릭으로 전송) | **그대로** — 앱이 내보내니 환경 무관 |
| **B. JVM** | SSH 후 `jcmd` 자유 | **ECS Exec 를 미리 켜야만** 접근 |
| **C. OS** | 전부 됨 | **프로세스 단위는 살고, 시스템 전체는 거짓말. `dmesg` 불가** |

**Fargate 함정 4가지**

| 함정 | 내용 | 대응 |
|---|---|---|
| **`/proc/meminfo` 가 호스트 값** | 512MB 태스크인데 `free -h` 는 호스트 수십 GB. `meminfo`·`cpuinfo` 는 네임스페이스가 안 걸림 | **`/sys/fs/cgroup/memory.max`·`memory.current` 가 진실**. `maps`·`smaps` 는 프로세스 단위라 **정상** |
| **`dmesg` 못 봄** | OOM Killer 흔적을 호스트 커널 로그에서 못 읽음 | `describe-tasks` 의 **`stoppedReason`** + 컨테이너 **`exitCode 137`**(=128+9 SIGKILL) + Container Insights |
| **사후에 못 붙음** | `enableExecuteCommand` 는 **태스크 기동 시** 결정. 장애 후 켜려면 재배포 → **문제 상태 소멸** | **처음부터 켜둔다** + SSM 권한. **JRE 아닌 JDK 이미지**여야 `jcmd`/`jmap` 존재 |
| **파일 휘발** | 힙덤프·JFR 파일이 태스크와 함께 사라짐. 덤프 크기가 임시 디스크 압박 | `-XX:HeapDumpPath` 를 **EFS 마운트**로, 또는 S3 업로드 |

**EC2 주의**: CloudWatch 기본 메트릭에 **메모리가 없다**(CPU·디스크·네트워크만). 하이퍼바이저는 게스트 내부를 못 보므로 **CloudWatch Agent 설치 필요** — "메모리 관측은 공짜가 아니다"의 실물.

**공통 필수 — JVM 컨테이너 인식** (§9.6 "RSS ≠ Java 힙"이 그대로 배포 규칙이 된다)

| `-Xmx` 설정 | 결과 |
|---|---|
| 안 줌 (JDK 10+, 컨테이너) | cgroup 한도의 **25%** 만 힙 (`MaxRAMPercentage` 기본값) — 너무 작음 |
| **태스크 메모리와 같게** | **위험** — 힙 밖(스레드·메타·코드캐시·direct)이 초과 → **exit 137** |
| **`-XX:MaxRAMPercentage=70`** | **권장** — 태스크 크기를 바꿔도 따라감 |

- **Fargate엔 스왑이 없다** → 한도 초과 시 완충 없이 즉사.
- **실습 3번을 로컬에서 해두면 이 실수를 안 한다** — 증상(에러 없이 증발)이 동일하고 흔적 찾는 곳만 `dmesg` → `stoppedReason` 으로 바뀔 뿐.

### 완료 기준
- `INFO`/`STATS` 로 QPS·히트율·p99·슬로우로그가 나온다.
- 위 실습 5개 중 **최소 1·3번**을 직접 재현하고 각 층 출력을 캡처해 회고에 남긴다.
- "같은 메모리를 세 층이 어떻게 다르게 부르는가"를 memory-model §9.5 표로 설명할 수 있다.
- (배포한다면) `-Xmx` 를 태스크 메모리와 같게 주면 왜 죽는지 설명할 수 있다.

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
