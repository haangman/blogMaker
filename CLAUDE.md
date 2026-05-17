# blogMaker

## 프로젝트 목적

요즘 가장 핫한 트렌드를 자동으로 수집·분석하고, 사람이 쓴 것처럼 자연스러운 블로그 글을 자동으로 작성해 **GitHub Pages 블로그**에 발행하는 프로젝트.

핵심은 두 가지:
1. **자연스러움** — AI 티가 나지 않게, 한 사람의 목소리/문체로 일관되게.
2. **자동화** — 글 생성·수정 시마다 자동으로 commit & push 되어 GitHub Pages가 즉시 업데이트.

## 핵심 요구사항

### 1. 트렌드 수집
- 최신 트렌드 소스: Google Trends, X(Twitter) 인기 키워드, Reddit r/popular, Naver 데이터랩, HackerNews 등
- 단순 키워드뿐 아니라 **왜 뜨고 있는지(맥락)** 까지 함께 수집해야 글의 깊이가 생긴다.
- 수집 결과는 `data/trends/YYYY-MM-DD.json` 같은 구조로 저장해 재현 가능성 확보.

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

### 3. GitHub Pages 블로그
- 정적 사이트 생성기: **Jekyll** (GitHub Pages 네이티브 지원 → 별도 빌드 액션 없이 자동 배포)
- 글 파일은 마크다운 + Front Matter (title, date, tags, summary)
- `_posts/YYYY-MM-DD-slug.md` 형식
- 이미지/썸네일은 `assets/img/` 하위로
- 테마는 `jekyll-remote-theme` 또는 minima 기반으로 시작 (확정 시 갱신)

### 4. 자동 commit & push
- **파일이 추가·수정될 때마다 자동으로 stage → commit → push**
- 커밋 메시지는 변경 내용을 요약 (예: `post: 새 글 "~~~" 발행`, `post: ~~~ 본문 수정`)
- 푸시는 main 브랜치로, GitHub Pages가 자동 빌드
- 실패(네트워크 오류, 충돌 등) 시 재시도 + 로그 남기기
- 자동화 수단: 파일 watcher 스크립트 또는 발행 함수 내부에서 `git add/commit/push`를 직접 호출

## 작업 시 지침 (Claude용)

### 코드 작성 시
- 트렌드 수집기, 글 생성기, 발행기를 **모듈 단위**로 분리 (책임 분리)
- 한 번에 한 글만 생성하는 단순 흐름을 먼저 만들고, 그 다음에 스케줄링/배치 추가
- 외부 API 호출은 항상 키를 `.env`에서 읽고 코드에 하드코딩하지 않는다. `.gitignore`에 반드시 `.env` 포함
- 글 발행 후 반드시 자동 commit & push가 트리거되는지 확인

### 글 품질 검수
글을 한 편 생성했으면 **발행 전에** 다음을 셀프체크:
- AI 정형 문구가 들어갔는가? → 있으면 다시 쓴다
- 문단 길이가 다 비슷한가? → 의도적으로 흔든다
- "여러분", "독자 여러분" 같은 호명이 어색하게 들어갔는가?
- 같은 단어/표현이 3회 이상 반복되는가?

### 커밋 메시지 컨벤션
- `post: ...` — 새 글 추가 또는 글 수정
- `feat: ...` — 생성기/수집기 등 기능 추가
- `fix: ...` — 버그 수정
- `chore: ...` — 설정/문서/의존성 등 잡일
- `style: ...` — 사이트 디자인/CSS

### 하지 말 것
- 사용자 확인 없이 GitHub 리포 삭제, force-push, 브랜치 제거
- `.env`나 API 키가 들어간 파일을 커밋
- "AI가 작성한 글입니다" 류의 주석/푸터를 글에 자동 삽입
- 모든 글을 동일한 템플릿(서론-본론-결론)으로 찍어내기

## 디렉토리 구조 (계획)

```
blogMaker/
├── CLAUDE.md                 # 이 문서
├── README.md                 # 사람용 소개
├── .gitignore
├── .env.example              # 환경변수 템플릿
├── config/
│   └── persona.md            # 블로그 화자 페르소나 정의
├── src/
│   ├── trends/               # 트렌드 수집 모듈
│   ├── writer/               # 글 생성 모듈 (자연스러움 로직 포함)
│   ├── publisher/            # 마크다운 변환 + git 자동화
│   └── main.py (또는 .ts)    # 엔트리포인트
├── data/
│   └── trends/               # 일자별 수집 결과
├── _posts/                   # Jekyll 글 (YYYY-MM-DD-slug.md)
├── assets/img/
├── _config.yml               # Jekyll 설정
├── Gemfile                   # github-pages gem
└── index.md                  # 블로그 홈
```

## 진행 상태

- [x] git init 및 GitHub 리포 연결
- [x] 정적 사이트 생성기 선택 → **Jekyll**
- [x] Jekyll 기본 구조 생성 (`_config.yml`, `Gemfile`, `index.md`, `_posts/`)
- [x] 페르소나 초안 작성 (`config/persona.md`) — 사용자 검토/수정 필요
- [ ] GitHub Pages 활성화 (Settings → Pages → main 브랜치)
- [ ] 트렌드 수집기 구현
- [ ] 글 생성기 구현 (자연스러움 가이드 반영)
- [ ] 자동 commit & push 파이프라인
- [ ] GitHub Pages 활성화 및 첫 글 발행
