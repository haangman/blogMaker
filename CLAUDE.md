# blogMaker

## 프로젝트 목적

요즘 가장 핫한 트렌드를 자동으로 수집·분석하고, 사람이 쓴 것처럼 자연스러운 블로그 글을 자동으로 작성해 **GitHub Pages 블로그**에 발행하는 프로젝트.

핵심은 두 가지:
1. **자연스러움** — AI 티가 나지 않게, 한 사람의 목소리/문체로 일관되게.
2. **자동화** — 글 생성·수정 시마다 자동으로 commit & push 되어 GitHub Pages가 즉시 업데이트.

## 멀티블로그 구조 (V4)

이 프로젝트는 **하나의 blogMaker (코드)** 가 **여러 개의 Jekyll 블로그**를 운영한다.

| 리포 | 역할 | 로컬 경로 |
|---|---|---|
| **blogMaker** | 자동 생성·발행 코드. 모든 블로그를 한 사이클에서 순차 처리. | `C:\Users\김은희\Downloads\blogMaker` |
| **J-Blog** (id: `trends`) | 일상 트렌드 블로그 (HN/Reddit/Google News/한국 매체). | `C:\Users\김은희\Downloads\J-Blog` → https://haangman.github.io/J-Blog/ |
| **J-Blog-AI** (id: `ai`) | AI 기술 블로그 (arXiv/HF Papers/Reddit ML+LocalLLaMA + 백로그). | `C:\Users\김은희\Downloads\J-Blog-AI` → https://haangman.github.io/J-Blog-AI/ |

세 리포 모두 **로컬 sibling 디렉토리**. publisher 는 BlogProfile.repo_name 으로 sanity check (디렉토리 이름 일치 안 하면 abort — 리포 혼동 방지).

> 글 변화는 해당 블로그 리포에 commit/push.
> 코드 변화는 blogMaker 에 commit/push.
> 세 git 히스토리가 모두 독립.

블로그 정의는 `config/blogs.yaml`. 새 블로그 추가는 yaml 한 줄 + 필요한 sources/categories/persona 파일만 만들면 자동으로 사이클에 포함.

## 핵심 요구사항

### 1. 트렌드 수집
- 최신 트렌드 소스: Google Trends, X(Twitter) 인기 키워드, Reddit r/popular, Naver 데이터랩, HackerNews 등
- 단순 키워드뿐 아니라 **왜 뜨고 있는지(맥락)** 까지 함께 수집해야 글의 깊이가 생긴다.
- 수집 결과는 `data/trends/YYYY-MM-DD.json` 같은 구조로 저장해 재현 가능성 확보 (blogMaker 안에 저장).

### 2. 사람처럼 쓰기 (가장 중요)
AI 글의 흔한 티를 의도적으로 피한다:
- "오늘은 ~에 대해 알아보겠습니다", "결론적으로", "요약하자면" 같은 정형 문구 금지
- 불릿 남발 금지 — 산문 위주, 불릿은 정말 목록일 때만
- 모든 문단을 균일한 길이로 만들지 말 것. 짧은 문장과 긴 문장을 섞는다.
- "사실은", "솔직히", "근데" 같은 구어체 연결을 적절히 사용
- 개인적 일화/관점/약한 의견을 한두 줄 끼워 넣기
- 결론을 강요하지 않고 열어두는 마무리도 OK
- 같은 표현 반복 회피 — 첫 문단과 마지막 문단의 단어 겹침을 의도적으로 줄인다
- **페르소나 일관성**: `config/persona.md`에 정의된 1인칭 화자(나이대, 직업, 말투, 자주 쓰는 표현, 싫어하는 표현)에 맞춰서 작성

### 3. Jekyll 블로그 (J-Blog 리포)
- 정적 사이트 생성기: **Jekyll** (GitHub Pages 네이티브 지원 → 별도 빌드 액션 없이 자동 배포)
- 글 파일은 마크다운 + Front Matter (title, date, tags, summary)
- 글 경로: `J-Blog/_posts/YYYY-MM-DD-slug.md`
- 이미지/썸네일: `J-Blog/assets/img/`
- 테마: minima 기본, 이후 변경 가능
- baseurl이 `/J-Blog`로 설정돼 있어 발행 URL은 `https://haangman.github.io/J-Blog/`

### 4. 자동 commit & push (보수적 정책)

**자동으로 push되는 것은 글(J-Blog)뿐.** 코드(blogMaker)는 자동 commit하지 않는다.

- **J-Blog (글)** → 자동
  - `_posts/`, `assets/img/`, `_drafts/`(드물게) 변화는 publisher가 직접 `git -C ../J-Blog add/commit/push`로 즉시 발행
  - 커밋 메시지 컨벤션: `post: 새 글 "~~~" 발행`, `post: ~~~ 본문 수정`, `style: ...` (사이트 디자인)
  - 푸시는 main 브랜치, GitHub Pages가 자동 빌드 (https://haangman.github.io/J-Blog/)
- **blogMaker (코드)** → 수동
  - 자동 시스템이 자기 자신을 push하는 건 위험 — 실패한 코드를 자동으로 메인에 올릴 수 있다
  - 코드/설정/페르소나 변경은 사람(또는 Claude Code 세션이 사용자 명시 요청을 받았을 때만) commit·push
  - `data/state.sqlite`, `data/trends/*`, `logs/` 등 런타임 산출물은 `.gitignore` 처리되어 애초에 push 대상이 아님

### 5. 실패 처리
- 외부 IO(수집·이미지·git push)는 모두 `tenacity` 지수 백오프 3회
- 어떤 단계든 실패해도 사이클은 **graceful하게 종료** — 다음 사이클이 idempotent하게 재시도
- 수집 0건이어도 사이클은 정상 종료

## 작업 시 지침 (Claude용)

### 코드 작성 시
- 트렌드 수집기, 글 생성기, 발행기를 **모듈 단위**로 분리 (책임 분리)
- 한 번에 한 글만 생성하는 단순 흐름을 먼저 만들고, 그 다음에 스케줄링/배치 추가
- 외부 API 호출은 항상 키를 `.env`에서 읽고 코드에 하드코딩하지 않는다. `.gitignore`에 반드시 `.env` 포함
- 발행기는 J-Blog의 절대/상대 경로를 환경변수(`JBLOG_PATH`)로 받아 처리한다. 기본값은 sibling `../J-Blog`
- 글 발행 후 반드시 J-Blog 쪽 자동 commit & push가 트리거되는지 확인

### 글 품질 검수
글을 한 편 생성했으면 **발행 전에** 다음을 셀프체크:
- AI 정형 문구가 들어갔는가? → 있으면 다시 쓴다
- 문단 길이가 다 비슷한가? → 의도적으로 흔든다
- "여러분", "독자 여러분" 같은 호명이 어색하게 들어갔는가?
- 같은 단어/표현이 3회 이상 반복되는가?

### 커밋 메시지 컨벤션
- `post: ...` — 새 글 추가 또는 글 수정 (J-Blog)
- `feat: ...` — 생성기/수집기 등 기능 추가 (blogMaker)
- `fix: ...` — 버그 수정
- `chore: ...` — 설정/문서/의존성 등 잡일
- `style: ...` — 사이트 디자인/CSS (J-Blog)

### 하지 말 것
- 사용자 확인 없이 GitHub 리포 삭제, force-push, 브랜치 제거
- `.env`나 API 키가 들어간 파일을 커밋
- "AI가 작성한 글입니다" 류의 주석/푸터를 글에 자동 삽입
- 모든 글을 동일한 템플릿(서론-본론-결론)으로 찍어내기
- blogMaker에 Jekyll 파일(`_posts/`, `_config.yml`, `Gemfile` 등)을 다시 만들지 말 것 — 그건 J-Blog 쪽

## 디렉토리 구조

### blogMaker (이 리포 — 코드)
```
blogMaker/
├── CLAUDE.md
├── .gitignore
├── .env.example
├── pyproject.toml
├── config/
│   ├── persona.md            # 사용자가 손으로 편집하는 원본
│   ├── persona.generated.md  # 톤 분석기 출력 (자동, 미생성)
│   ├── sources.yaml          # 수집 소스 정의
│   ├── categories.yaml       # 카테고리 enum
│   └── quality_rules.yaml    # 정형구/금칙어 regex
├── src/
│   ├── main.py               # Task Scheduler 호출 — 한 사이클
│   ├── cli.py                # typer 기반 health/init/dry-run/run/analyze-persona
│   ├── config_loader.py      # pydantic-settings + yaml
│   ├── logging_setup.py      # structlog + 키 마스킹
│   ├── llm/                  # Claude Code CLI 호출 게이트 (Step 4)
│   ├── collectors/           # 소스별 1파일 + registry
│   ├── normalize/            # 본문 추출·언어 감지·1차 디둡
│   ├── cluster/              # 임베딩 → HDBSCAN → 사건 통합
│   ├── categorize/           # 카테고리 분류
│   ├── selector/             # 토픽 스코어링
│   ├── persona/              # fetcher/analyzer/merger (CLI에서만)
│   ├── writer/               # prompts/generator/postprocess
│   ├── images/               # unsplash/pexels/attribution
│   ├── quality/              # rules/ai_smell/stats/persona_check/gate
│   ├── publisher/            # frontmatter/jekyll_writer/asset_copier/git_push
│   ├── state/                # SQLite (schema.sql, db.py)
│   └── utils/                # lockfile/timeutil/retry/http
├── data/                     # 런타임 산출물 (gitignored)
├── logs/                     # 사이클 로그 (gitignored)
├── scripts/                  # run_cycle.ps1, setup_task.ps1, task_blogmaker.xml
└── tests/
```

### J-Blog (sibling 리포 — 블로그)
```
J-Blog/
├── _config.yml               # Jekyll 설정 (baseurl: /J-Blog)
├── Gemfile                   # github-pages gem
├── index.md                  # 블로그 홈
├── _posts/                   # 글: YYYY-MM-DD-slug.md
├── assets/img/               # 이미지
└── .gitignore
```

## 진행 상태

- [x] blogMaker git init 및 GitHub 리포 연결
- [x] 정적 사이트 생성기 선택 → **Jekyll**
- [x] 페르소나 초안 작성 (`config/persona.md`) — 사용자 검토/수정 필요
- [x] 블로그를 별도 리포(**J-Blog**)로 분리하고 Pages 활성화 → https://haangman.github.io/J-Blog/
- [x] 전체 설계 plan 승인 (`~/.claude/plans/enumerated-sauteeing-frog.md`)
- [x] **Step 1: Scaffold** — pyproject, config_loader, logging_setup, SQLite 스키마, 잠금 파일, 기본 yaml들
- [x] **Step 2: Publisher** — J-Blog 자동 commit/push + 리포 sanity 가드 + dry-run CLI
- [x] **Step 3: Collectors v1** — base/Collector + HackerNews + normalize + 1차 dedupe
- [x] **Step 4: Claude CLI 게이트 + writer + quality gate v1** — `claude -p --output-format json` subprocess + tenacity + DB 기록, writer 재작성 루프
- [x] **Step 5: cluster + categorize + selector** — sentence-transformers + HDBSCAN(폴백 코사인+union-find) + simhash 매칭 + 카테고리 다양성 페널티
- [x] **Step 6: persona analyzer CLI** — `analyze-persona --url ...` 으로 RSS/sitemap 수집 → 톤 분석 → `persona.generated.md` 자동 생성
- [x] **Step 7: 이미지 + 게이트 확장** — Unsplash → Pexels 폴백, 통계/페르소나 체크 + must_contain_any 검사
- [x] **Step 8: 나머지 collectors + follow-up 모드** — Reddit/Google News(ko·en)/BBC/KoreanNews(연합·ETNews·한겨레)/Lobsters 활성화, source_health로 3연속 실패 시 자동 비활성
- [x] **Step 9: Windows Task Scheduler 설정** — `scripts/run_cycle.ps1` 래퍼, `scripts/setup_task.ps1` 자동 등록 스크립트, `scripts/task_blogmaker.xml` 참고 템플릿
- [x] **V2: 글 친절도 + 다중 이미지 마커** — 길이 800~2400자 위주, `[IMAGE: "..."]` 마커 시스템(헤더 1장 + 본문 0~3장), 이미지 키워드 프롬프트 구체화
- [x] **V3: 일상 토픽 우선 + 사이클당 5편 + 중복 30일**
    - selector 점수에 `lifestyle` 가중치 영구 적용 (HN/Lobsters 0.10, Reddit popular 0.90, 한국 매체 0.85)
    - `pick_topics(n=5)` 다중 선정 + in-cycle simhash 가드
    - 중복 가드 윈도우 7일 → **30일** (`DUPLICATE_WINDOW_DAYS`)
    - follow-up 윈도우 8~30일 → **30~90일** (중복 가드와 겹치지 않게)
    - `ARTICLES_PER_CYCLE`, `DUPLICATE_WINDOW_DAYS` 환경변수 추가

### Task Scheduler 등록 (사용자가 실행)
```powershell
cd C:\Users\김은희\Downloads\blogMaker
pwsh -ExecutionPolicy Bypass -File .\scripts\setup_task.ps1            # 매일 09:00 등록
pwsh -ExecutionPolicy Bypass -File .\scripts\setup_task.ps1 -At "21:00" # 시각 변경
Start-ScheduledTask -TaskName 'Cycle' -TaskPath '\BlogMaker\'           # 수동 1회 트리거
pwsh -ExecutionPolicy Bypass -File .\scripts\setup_task.ps1 -Remove     # 작업 제거
```
사용자 로그온 시 실행 — Claude Code CLI 세션이 사용자 컨텍스트에 묶이므로 다른 옵션 불가.

### Google Search Console (GSC) 등록 — 한 번만 하면 됨

신규 사이트가 Google 검색에 노출되려면 GSC 등록 + sitemap 제출이 가장 큰 단축.
두 블로그 각각 등록한다.

1. https://search.google.com/search-console 접속 (Google 계정 로그인)
2. "속성 추가" → **URL 접두사** 선택
3. URL 입력: `https://haangman.github.io/J-Blog/` (J-Blog-AI 는 별도 등록)
4. 소유권 확인 → **HTML 태그** 방식 선택
5. 받은 토큰 (`<meta name="google-site-verification" content="여기값">` 의 content 값)
6. `J-Blog/_config.yml` 의 `google_site_verification:` 필드에 그 값 붙여넣기
7. commit + push → GitHub Pages 빌드 1~2분 대기
8. GSC 로 돌아가서 '확인' 클릭 → 소유권 인정
9. 좌측 메뉴 **Sitemaps** → `sitemap.xml` 입력 → 제출
10. 며칠~수 주 후 **Coverage / Pages** 에서 색인된 글 수 확인. `site:haangman.github.io/J-Blog` 로 Google 검색해서 직접 확인도 가능

같은 절차를 **J-Blog-AI 에도** 반복 (verification 토큰은 별도 발급).

신규 사이트는 첫 페이지 인덱싱까지 ~3~14일, 글 페이지는 그 뒤 점진적으로. 즉시 결과 안 보여도 정상.

### 운영 메모 — 사이클 강제 종료
사이클을 도중에 멈춰야 한다면 **lock 파일을 먼저 지우지 말 것**. 잠금 가드는 PID 살아있는지 확인하는데, lock 만 먼저 지우면 살아있는 python 이 새 사이클과 동시에 돌면서 LLM 호출이 폭주할 수 있다 (구독 quota 빠르게 소진). 안전 순서:

```powershell
# 1) 실제로 도는 python 프로세스를 먼저 잡는다
Get-Process python -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like '*blogMaker*' } |
  Stop-Process -Force

# 2) 그 후 lock 파일 정리 (보통 자동으로 사라지지만 안 사라지면 수동)
Remove-Item C:\Users\김은희\Downloads\blogMaker\data\.cycle.lock -ErrorAction SilentlyContinue
```

추가 보호: `.env` 의 `MAX_LLM_CALLS_PER_CYCLE` (기본 80) 으로 한 사이클 내 LLM 호출 횟수가 상한 초과 시 자동 abort.

### 의존성 설치 (사용자가 실행)
```powershell
cd C:\Users\김은희\Downloads\blogMaker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env   # 그 후 키 값 채워넣기
python -m src.cli init
python -m src.cli health
```
