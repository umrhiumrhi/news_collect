# news_collect

뉴스 **RSS / Google News(GN)** 수집 → 본문 추출 → **PostgreSQL** 적재 API 서버입니다.

| | |
|--|--|
| **프레임워크** | **FastAPI** (ASGI) |
| **서버** | **Uvicorn** (`python app.py` 또는 `uvicorn app:app`) |
| **포트(개발)** | `5000` |
| **데이터 SoT** | PostgreSQL `sources` / `articles` |
| **UI 출처 목록** | `categories.json` (테스트 UI·관리용, 배치 SoT 아님) |

> 이전에는 Flask 기반이었으나 **FastAPI로 이전**했습니다.  
> REST 경로·요청 body·NDJSON 스트림 형식은 동일하게 유지했습니다. 프론트는 Base URL만 맞으면 대부분 그대로 동작합니다.

### 바로 가기

| 항목 | URL |
|------|-----|
| 테스트 UI | http://127.0.0.1:5000/ |
| OpenAPI (Swagger UI) | http://127.0.0.1:5000/docs |
| ReDoc | http://127.0.0.1:5000/redoc |
| OpenAPI JSON | http://127.0.0.1:5000/openapi.json |

| 계층 | 역할 | 프론트가 쓸 때 |
|------|------|----------------|
| `categories.json` | 테스트 UI용 출처·키워드 목록 | `GET /api/categories` (관리/미리보기 목록) |
| PostgreSQL `sources` | 수집 가능 원천 + GN 파생 출처 | 배치·저장 결과·통계 |
| PostgreSQL `articles` | 실제 기사 본문·URL | **제품 뉴스 목록/상세의 주 데이터** (현재 목록 API는 없음 → 직접 조회 또는 추후 API) |

> **프론트 개발자 한 줄 요약**  
> - 사이드바 “키워드/언론사 목록” ≠ DB 기사 목록  
> - 기사를 앱에 보여주려면 **`articles` 테이블**(또는 향후 목록 API)을 써야 함  
> - 수집 트리거는 REST API, 긴 작업은 **NDJSON 스트림** 권장  
> - API 스펙 탐색은 **`/docs`** 권장  

---

## 목차

1. [아키텍처 & 데이터 흐름](#1-아키텍처--데이터-흐름)
2. [설정 & 실행](#2-설정--실행)
3. [DB 스키마와 연결성](#3-db-스키마와-연결성)
4. [소스 유형 (RSS / GN 원천 / GN 파생)](#4-소스-유형-rss--gn-원천--gn-파생)
5. [API 전체 명세](#5-api-전체-명세)
6. [NDJSON 스트림 사용법](#6-ndjson-스트림-사용법)
7. [프론트 연동 시나리오](#7-프론트-연동-시나리오)
8. [응답 객체 스키마](#8-응답-객체-스키마)
9. [주의사항 & FAQ](#9-주의사항--faq)

---

## 1. 아키텍처 & 데이터 흐름

```
┌─────────────────┐     REST / NDJSON      ┌────────────────────────────────┐
│  Frontend App   │ ──────────────────────► │  Uvicorn (ASGI)                │
│  (or Test UI)   │ ◄────────────────────── │    └─ FastAPI app (app.py)     │
└─────────────────┘      /docs OpenAPI     │         port 5000              │
                                           └───────────────┬────────────────┘
                                                           │
                     ┌─────────────────────────────────────┼──────────────────────┐
                     │                                     │                      │
                     ▼                                     ▼                      ▼
            categories.json                       RSS / Google News         PostgreSQL
            (UI 출처 목록)                          본문 스크래핑              sources
                    │                                                        articles
                    │  (add-source 시 GN 원천은 sources 에도 등록)
                    └──────────────────────────────────────────────────────────┘
```

**구현 메모 (FastAPI)**

| 기능 | 구현 |
|------|------|
| JSON API | 라우트 함수 `return dict` → 자동 JSON |
| 에러 응답 | `JSONResponse(..., status_code=4xx/5xx)` |
| 진행 스트림 | `StreamingResponse` + `media_type=application/x-ndjson` |
| CORS | `CORSMiddleware` (`allow_origins=["*"]`) |
| 정적 파일 | `app.mount("/static", StaticFiles(...))` |
| 테스트 UI | `GET /` → `FileResponse(templates/index.html)` |
| 자동 문서 | `/docs`, `/redoc`, `/openapi.json` |

### 1.1 미리보기만 (DB 안 씀)

```
POST /api/fetch-stream
  → RSS 파싱 → (GN이면 URL 해석) → 본문 추출
  → JSON articles[] 반환
  → DB INSERT 없음
```

### 1.2 단건 수집 + DB 저장 (제품 배치에 가장 가까움)

```
POST /api/fetch-and-save-stream
  → 수집 (위와 동일)
  → db.save_articles_to_db(...)
       · RSS: sources upsert(name, rss_url) → articles insert
       · GN:  기사마다 publisher 기준 파생 sources upsert
              → articles insert (본문 있는 건만)
  → { saved, skipped, no_content, errors }
```

### 1.3 전체 배치 저장 (운영 권장 경로)

```
POST /api/save-all-stream
  → SELECT 수집 가능 sources  (http(s) RSS, GN 파생 제외)
  → 각 소스 병렬 수집 + 저장
  → categories.json 과 무관 (그 순간 DB sources 만 기준)
```

### 1.4 UI 출처 등록

```
POST /api/add-source
  · RSS: categories.json 에만 추가 (첫 저장 시 sources 생성)
  · GN:  categories.json + sources 에 원천 행 동시 등록
         name = "Google News · {keyword}"
         rss_url = https://news.google.com/rss/search?q=...

POST /api/delete-source
  · categories.json 에서만 삭제
  · DB sources / articles 는 자동 삭제하지 않음
```

---

## 2. 설정 & 실행

### 2.1 요구 사항

- Python 3.11+ 권장  
- PostgreSQL 14+ (개발 환경 예: 18)  
- **pgvector** 확장 (`title_embedding` 컬럼용, 임베딩 값 채우기는 별도 파이프라인)

### 2.2 의존 패키지

```bash
pip install -r requirements.txt
```

| 구분 | 패키지 |
|------|--------|
| 웹 | `fastapi`, `uvicorn[standard]`, `python-multipart` |
| 수집 | `feedparser`, `requests`, `urllib3`, `curl_cffi`, `googlenewsdecoder` |
| 본문 | `beautifulsoup4`, `readability-lxml` |
| DB | `psycopg[binary]` (v3), PostgreSQL + **pgvector** |
| 기타 | `python-dateutil` |

### 2.3 DB 설정

1. DB 생성 후 스키마 적용:

```bash
psql -U postgres -d news_collect -f schema.sql
# 기존 DB에 임베딩 컬럼만 추가한 경우:
# psql -U postgres -d news_collect -f migrations/001_title_embedding.sql
```

2. `config.example.json` 을 복사해 `config.json` 작성 (**저장소에 커밋하지 말 것**):

```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "dbname": "news_collect",
    "user": "postgres",
    "password": "YOUR_PASSWORD"
  }
}
```

### 2.4 서버 실행 (FastAPI + Uvicorn)

**개발 (권장 — reload 포함)**

```bash
cd news_collect
python app.py
```

`app.py` 의 `__main__` 이 내부적으로 다음을 실행합니다:

```python
uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
```

**동일 동작 (직접 실행)**

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 5000 --reload
```

| 항목 | 값 |
|------|-----|
| ASGI 앱 경로 | `app:app` → 파일 `app.py` 의 `app = FastAPI(...)` |
| Base URL | `http://127.0.0.1:5000` |
| 테스트 UI | `http://127.0.0.1:5000/` |
| Swagger | `http://127.0.0.1:5000/docs` |
| CORS | 전역 허용 — 로컬 분리 포트 프론트 가능 |
| 인증 | **없음** (내부망·개발용 가정) |

**운영 예시 (reload 끄고 바인딩)**

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 5000 --workers 1
```

> 수집·본문 추출은 **동기 I/O + 스레드 풀** 입니다.  
> 워커 수를 크게 늘리기 전에 DB·외부 사이트 부하를 확인하세요.  
> (구 Flask `app.run()` / gunicorn WSGI 는 사용하지 않습니다.)

---

## 3. DB 스키마와 연결성

### 3.1 ER (개념)

```
sources 1 ──────< articles
   │                  │
   │ source_id (PK)   │ article_id (PK)
   │ name             │ source_id (FK) → sources
   │ rss_url UNIQUE   │ source_url UNIQUE  ← 기사 중복 키
   │ source_type      │ title
   │ credibility_     │ cleaned_content   ← 본문(제품 표시용)
   │   weight         │ raw_content       ← 원문 HTML
   │ created_at       │ published_at
                      │ collected_at
                      │ status
                      │ title_embedding vector(1536)  ← 유사검색용, 현재 자동 미기입
```

### 3.2 `sources` — 출처

| 컬럼 | 설명 |
|------|------|
| `source_id` | PK |
| `name` | 표시명. 예: `매일경제 - 경제`, `Google News · 우주`, `한화시스템 - 우주 (GN)` |
| `rss_url` | UNIQUE. 실제 `https://...` 또는 파생용 `google_news://키워드/언론사` |
| `source_type` | DB 신뢰도 분류: `공식발표` \| `통신사` \| `전문미디어` \| `포털API` \| `커뮤니티` (이름 휴리스틱) |
| `credibility_weight` | 0~1 |

**프론트 주의:**  
`categories.json` 의 `type: "RSS" | "GOOGLE_NEWS"` 와  
DB `sources.source_type` (`전문미디어` 등) 은 **다른 축**입니다.

### 3.3 `articles` — 기사

| 컬럼 | 설명 | 프론트 활용 |
|------|------|-------------|
| `article_id` | PK | 상세 키 |
| `source_id` | FK | 언론사/출처 조인 |
| `source_url` | **UNIQUE** 원문 URL | 링크 이동, 중복 방지 |
| `title` | 제목 | 목록 |
| `cleaned_content` | 정제 본문 | 본문 표시·요약 입력 |
| `raw_content` | 원문 HTML | 보통 비노출 |
| `published_at` | RSS 발행 시각 | 정렬 |
| `collected_at` | 수집 시각 | “오늘 수집분” 필터 |
| `status` | `collected` → `processed` → `summarized` → `archived` | 파이프라인 단계 (현재 대부분 `collected`) |
| `title_embedding` | `vector(1536)`, NULL 허용 | 의미 검색 (값 채우는 워커 별도) |

### 3.4 저장 규칙 (백엔드 고정 정책)

| 조건 | 동작 |
|------|------|
| 본문 추출 실패 / 빈 본문 | **INSERT 안 함** (`no_content`) |
| 동일 `source_url` 재수집 | **INSERT 안 함** (`skipped` / 중복). 기존 행 **UPDATE 없음** |
| GN 수집 | 기사별 `publisher` 로 파생 `sources` 생성 후 그 `source_id` 에 기사 연결 |
| 도메인형 publisher (`v.daum.net` 등) | 본문 HTML `og:site_name` 으로 언론사명 보강 후 저장 |

### 3.5 수집 가능 sources (전체 저장 대상)

`list_collectible_sources()` 조건:

```sql
rss_url LIKE 'http://%' OR rss_url LIKE 'https://%'
AND rss_url NOT LIKE 'google_news://%'
AND name NOT LIKE '% (GN)'
```

| 포함 | 제외 |
|------|------|
| 일반 언론 RSS | `google_news://증권/한화시스템` 파생 |
| `https://news.google.com/rss/search?...` GN **원천** | 이름 끝이 ` (GN)` 인 행 |

---

## 4. 소스 유형 (RSS / GN 원천 / GN 파생)

| 종류 | `categories.json` 예 | DB `sources` 예 | 전체 저장 | 기사 적재 |
|------|----------------------|-----------------|-----------|-----------|
| 일반 RSS | `type: RSS`, `url: https://www.mk.co.kr/...` | 동일 name/url | ✅ | 해당 source_id |
| GN 원천 | `type: GOOGLE_NEWS`, `keyword: 우주` | `Google News · 우주` + google RSS URL | ✅ (키워드 검색 재실행) | 파생 소스로 분산 저장 |
| GN 파생 | (목록에 안 넣음) | `매일경제 - 우주 (GN)` + `google_news://우주/매일경제` | ❌ | GN 수집 시 생성·적재 |

```
[GN 원천 수집 1회]
  keyword = "우주"
  → 기사들 publisher 보강 (og:site_name)
  → sources: "MBC 뉴스 - 우주 (GN)", "매일경제 - 우주 (GN)", ...
  → articles: 각 파생 source_id 로 INSERT
```

**UI에 보이는 “키워드”** = `categories.json` 의 GN 항목 (`keyword` 필드).  
**DB에 쌓인 기사 출처명** = 파생 `sources.name` (언론사 + 키워드 + `(GN)`).

---

## 5. API 전체 명세

Base: `http://localhost:5000`  
Content-Type: `application/json` (POST body)  
스트림: 응답 `Content-Type: application/x-ndjson` (`StreamingResponse`)

대화형 스펙: **http://localhost:5000/docs** (FastAPI 자동 생성 OpenAPI)

### 5.1 요약 표

| Method | Path | DB | 용도 |
|--------|------|----|------|
| GET | `/` | - | 테스트 HTML UI |
| GET | `/api/categories` | 파일 | 출처·키워드 목록 |
| POST | `/api/add-source` | 파일 (+ GN 시 sources) | 출처/키워드 추가 |
| POST | `/api/delete-source` | 파일만 | 목록에서 삭제 |
| POST | `/api/fetch` | - | 수집 (동기 JSON) |
| POST | `/api/fetch-stream` | - | 수집 + 진행 스트림 ★ |
| POST | `/api/fetch-and-save` | ✅ | 수집+저장 동기 |
| POST | `/api/fetch-and-save-stream` | ✅ | 수집+저장 스트림 ★ |
| POST | `/api/save-all` | ✅ | DB 전체 배치 동기 |
| POST | `/api/save-all-stream` | ✅ | DB 전체 배치 스트림 ★ |
| GET | `/api/db-stats` | ✅ | 건수·상위 출처 |
| GET | `/api/test` | - | categories 피드 스모크 |

★ = 프론트 UX용 권장

---

### 5.2 `GET /api/categories`

**응답**

```json
{
  "categories": {
    "경제/경영": [
      {
        "name": "매일경제 - 경제",
        "url": "https://www.mk.co.kr/rss/30100041/",
        "type": "RSS"
      },
      {
        "name": "Google News · 우주",
        "url": "https://news.google.com/rss/search?q=%EC%9A%B0%EC%A3%BC&hl=ko&gl=KR&ceid=KR:ko",
        "type": "GOOGLE_NEWS",
        "keyword": "우주",
        "source_id": 165,
        "db_created": true
      }
    ],
    "IT": [ ... ],
    "국제": [ ... ],
    "문화/건강": [ ... ]
  }
}
```

| 필드 | 설명 |
|------|------|
| `type` | `RSS` \| `GOOGLE_NEWS` |
| `keyword` | GN 전용. 화면 라벨·수집 시 `keyword` 파라미터로 전달 |
| `url` | 실제 피드 URL (수집 요청에 그대로 사용) |
| `source_id` | GN 추가 시 DB 원천 id (없을 수 있음) |

---

### 5.3 `POST /api/add-source`

**Body — 일반 RSS**

```json
{
  "category": "경제/경영",
  "type": "RSS",
  "name": "매일경제 - 경제",
  "url": "https://www.mk.co.kr/rss/30100041/"
}
```

**Body — Google News 키워드**

```json
{
  "category": "경제/경영",
  "type": "GOOGLE_NEWS",
  "keyword": "우주"
}
```

- `url` 은 서버가 자동 생성 (`hl=ko&gl=KR&ceid=KR:ko`)  
- DB `sources` 에 원천 등록 실패 시 **500** (categories 도 롤백에 가깝게 실패 응답)

**성공**

```json
{
  "success": true,
  "message": "\"Google News · 우주\" 추가됨 · sources 등록 (id=…)",
  "categories": { "...전체...": "..." },
  "source": { "name": "...", "url": "...", "type": "GOOGLE_NEWS", "keyword": "우주", "source_id": 1 }
}
```

**에러:** `400` 필수값, `409` 중복 키워드/URL, `500` 예외

---

### 5.4 `POST /api/delete-source`

```json
{
  "category": "경제/경영",
  "source_name": "Google News · 우주"
}
```

- `source_name` 은 `categories` 항목의 **`name`** 과 일치  
- **DB 행은 삭제되지 않음**

---

### 5.5 수집 공통 파라미터 (`fetch*`, `fetch-and-save*`)

```json
{
  "url": "https://...",
  "type": "RSS",
  "name": "매일경제 - 경제",
  "keyword": null,
  "limit": null,
  "include_yesterday": false
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `url` | ✅ | 피드 URL |
| `type` / `source_type` | | `RSS`(기본) / `GOOGLE_NEWS` / `GN` … |
| `name` | | 로그·(비-GN) 저장 시 sources 이름 |
| `keyword` | GN 시 권장 | 파생 소스명 `언론사 - {keyword} (GN)` 에 사용 |
| `limit` | | 피드 entry 상위 N개만 (날짜 필터 전) |
| `include_yesterday` | | `true` 면 로컬 기준 오늘+어제 |

**날짜 필터:** 기본은 **로컬 타임존 “오늘”** 발행 기사만.

---

### 5.6 `POST /api/fetch` · `POST /api/fetch-stream`

- **DB 미사용**  
- 동기: 최종 JSON 한 방  
- 스트림: progress 라인 + done (아래 §6)

**성공 시 `data` (또는 동기 응답 루트)**

```json
{
  "success": true,
  "title": "피드 타이틀",
  "articles": [ /* Article 객체 배열 — §8 */ ],
  "count": 100,
  "today_articles": 12,
  "failed": 2,
  "is_google_news": true,
  "keyword": "우주"
}
```

`failed`: 본문 추출 실패 건수 (배열에는 `content: "본문을 가져올 수 없습니다."` 로 들어감).  
DB 저장 API 는 이런 건을 **넣지 않음**.

---

### 5.7 `POST /api/fetch-and-save` · `POST /api/fetch-and-save-stream`

수집 후 DB 저장.

**성공 `data` 예**

```json
{
  "success": true,
  "feed_title": "...",
  "today_articles": 12,
  "failed": 2,
  "db": {
    "saved": 8,
    "skipped": 2,
    "no_content": 2,
    "errors": 0
  }
}
```

| `db.*` | 의미 |
|--------|------|
| `saved` | 신규 INSERT |
| `skipped` | `source_url` 중복 |
| `no_content` | 본문 없어 저장 안 함 |
| `errors` | 기타 오류 |

---

### 5.8 `POST /api/save-all` · `POST /api/save-all-stream`

- Body 없음  
- **`categories.json` 무시**, DB 수집 가능 sources 만  
- 소스가 0개면 저장 0 + 메시지성 progress

**성공 `data` 예**

```json
{
  "total_saved": 40,
  "total_skipped": 100,
  "total_no_content": 5,
  "detail": [
    {
      "success": true,
      "name": "매일경제 - 경제",
      "source_id": 1,
      "today_articles": 3,
      "db": { "saved": 1, "skipped": 2, "no_content": 0, "errors": 0 }
    }
  ],
  "parallel": {
    "feed_workers": 4,
    "article_workers_per_feed": 4
  }
}
```

동기 `/api/save-all` 은 `{ "success": true, ...위 필드 }` 형태.

---

### 5.9 `GET /api/db-stats`

```json
{
  "success": true,
  "sources_count": 56,
  "articles_count": 1400,
  "top_sources": [
    { "name": "매일경제 - 경제", "article_count": 120 }
  ]
}
```

기사 **목록/검색 API는 아직 없음**. 제품 피드 UI는:

- DB를 직접 읽거나  
- 백엔드에 `GET /api/articles?...` 를 추가하는 방향  

을 협의하세요.

---

## 6. NDJSON 스트림 사용법

FastAPI 에서 `StreamingResponse` 로 전송합니다.  
Flask 시절과 **줄 단위 JSON 프로토콜은 동일**합니다.

### 6.1 형식

- MIME: `application/x-ndjson`  
- **한 줄 = JSON 객체 하나** + `\n`  
- 라인 종류:

```json
{"type":"progress","message":"…","phase":"collecting","feed":"…","current":3,"total":10}
{"type":"done","success":true,"data":{ ... 최종 결과 ... }}
{"type":"done","success":false,"error":"..."}
```

`phase` 예: `start`, `fetch_rss`, `collect_start`, `collecting`, `collect_done`, `saving`, `saved`, `feed_start`, `batch_start`, `error`, `feed_error`, `done` …

### 6.2 프론트 파싱 패턴 (권장)

```js
async function readNdjsonStream(response, onProgress) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let finalPayload = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      const obj = JSON.parse(line);
      if (obj.type === 'progress') onProgress?.(obj);
      if (obj.type === 'done') finalPayload = obj;
    }
  }
  return finalPayload; // { type:'done', success, data? | error? }
}

// 사용 예
const res = await fetch('http://localhost:5000/api/fetch-and-save-stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    url: source.url,
    type: source.type,
    name: source.name,
    keyword: source.keyword || null,
  }),
});
const final = await readNdjsonStream(res, (p) => console.log(p.message));
if (!final?.success) throw new Error(final?.error || '실패');
const { db, today_articles } = final.data;
```

> `response.json()` 한 번에 파싱하면 **안 됩니다.** 반드시 **줄 단위** 처리.

참고 구현: 저장소 `static/script.js` 의 `readNdjsonStream`.

---

## 7. 프론트 연동 시나리오

### A. 관리 화면 — 출처/키워드 목록

1. `GET /api/categories`  
2. 카테고리 탭 + 소스 버튼 렌더  
   - RSS: `source.name`  
   - GN: `source.keyword` 또는 `Google News · {keyword}`  
3. 추가: `POST /api/add-source`  
4. 삭제: `POST /api/delete-source` (**DB 기사는 남음**)

### B. 미리보기 (저장 없이 기사 카드)

1. 사용자가 소스 선택  
2. `POST /api/fetch-stream` + NDJSON 진행바  
3. `final.data.articles[]` 로 카드 렌더  
4. 필드: `title`, `content`, `link`, `published`, `publisher`, `method`

### C. “이 소스 수집해서 DB에 넣기”

1. `POST /api/fetch-and-save-stream`  
2. 완료 후 `final.data.db` 로 토스트  
3. 실제 목록은 DB `articles` 재조회 (또는 stats 만 갱신)

### D. 매일 배치 / “전체 저장” 버튼

1. `POST /api/save-all-stream` (타임아웃 여유 있게 — 수 분 가능)  
2. progress 로 피드별 진행 표시  
3. `GET /api/db-stats` 로 카운트 갱신  

**중요:** 전체 저장 전 DB에 **수집 가능 sources** 가 있어야 함.  
`categories.json` 만 있고 `sources` 가 비면 **0건**.

### E. 제품 홈 — “오늘 뉴스 5건” (현재 백엔드 미구현)

권장 방향 (백엔드 추가 전 임시):

```sql
SELECT a.article_id, a.title, a.cleaned_content, a.source_url,
       a.published_at, a.collected_at, s.name AS source_name
FROM articles a
JOIN sources s ON s.source_id = a.source_id
WHERE a.collected_at::date = CURRENT_DATE
  AND a.cleaned_content IS NOT NULL
ORDER BY a.published_at DESC NULLS LAST
LIMIT 50;
```

이후 앱에서 키워드 필터·중복 제거·Top 5 선정.  
장기적으로는 `GET /api/articles?date=...&keyword=...&limit=5` 추가를 요청하세요.

---

## 8. 응답 객체 스키마

### 8.1 Article (수집 API 메모리 객체)

| 필드 | 타입 | 설명 |
|------|------|------|
| `title` | string | 제목 (GN 은 끝의 ` - 언론사` 제거된 형태) |
| `content` | string \| 실패 문구 | 본문 텍스트 |
| `raw_content` | string \| null | 원문 HTML (저장 시 `raw_content` 컬럼) |
| `link` | string | 원문 URL (GN 은 해석된 최종 URL) |
| `published` | string | RSS 발행 문자열 |
| `method` | string | 추출 방법 (`Readability`, `JSON-LD`, `BeautifulSoup`, `실패`, 사이트 전용 등) |
| `publisher` | string \| null | 언론사 (주로 GN; og:site_name 보강 가능) |
| `keyword` | string \| null | GN 키워드 |

DB `articles` 컬럼 매핑:

| Article | DB |
|---------|-----|
| `link` | `source_url` |
| `content` | `cleaned_content` |
| `raw_content` | `raw_content` |
| `published` | `published_at` (파싱) |
| (없음) | `collected_at` = 저장 시각 |
| `publisher` | 직접 컬럼 없음 → **`sources.name`** 에 반영 (특히 GN 파생) |

---

## 9. 주의사항 & FAQ

### Q. Flask 때랑 API가 바뀌었나요?
**경로·body·NDJSON 프로토콜은 동일**합니다.  
바뀐 것: 서버가 **FastAPI + Uvicorn**, 문서 URL **`/docs`**, 정적 파일 **`/static/...`**.  
프론트는 `fetch('/api/...')` 그대로 쓰면 됩니다.

### Q. 서버를 어떻게 띄우나요?
```bash
python app.py
# 또는
python -m uvicorn app:app --host 127.0.0.1 --port 5000 --reload
```
Flask의 `app.run()` 은 더 이상 없습니다.

### Q. 프론트 키워드 목록이 DB랑 다릅니다
**정상입니다.** 목록 = `categories.json`, 배치/기사 = `sources`/`articles`.  
GN 추가는 둘 다 쓰지만, 삭제·수동 SQL 이후 어긋날 수 있습니다.

### Q. 전체 저장이 0건입니다
- `sources` 가 비었거나  
- GN **파생**만 있고 **원천/일반 RSS** 가 없음  

→ `GET /api/db-stats` 와 DB에서 수집 가능 조건으로 확인.

### Q. 같은 뉴스가 두 번 안 들어갑니다
`source_url` UNIQUE. 두 번째부터 `skipped`. 본문 개선 재수집으로 **덮어쓰지 않음**.

### Q. GN 인데 언론사가 도메인으로 나옵니다
일부 항목은 Google 이 도메인만 줌. 본문 수집 성공 시 `og:site_name` 으로 보강. 본문 실패 시 도메인 유지.

### Q. `title_embedding` 은 언제 채워지나요
컬럼·IVFFlat 인덱스만 준비됨. 임베딩 API 연동 워커는 **미구현**. NULL 인 채로 수집 가능.

### Q. 인증은요?
없음. 프로덕션 노출 시 게이트웨이 인증·내부망 필수.

### Q. 동기 vs 스트림 중 무엇을 쓰나요?
| 상황 | 권장 |
|------|------|
| 버튼 UX / 진행 로그 | `*-stream` (`StreamingResponse`) |
| cron 단순 호출 | `save-all` 또는 stream + 로그 |
| 타임아웃 짧은 프록시 | stream + 긴 timeout |

수집은 네트워크·본문 추출로 **수십 초~수 분** 걸릴 수 있습니다.

---

## 디렉터리 안내

```
news_collect/
├── app.py                 # FastAPI 앱 + 라우트 + 수집/추출 로직
├── db.py                  # PostgreSQL 접근, 저장, 통계
├── requirements.txt       # fastapi, uvicorn, psycopg, ...
├── schema.sql             # 전체 스키마 (pgvector 포함)
├── migrations/            # 증분 마이그레이션
├── categories.json        # UI/설정용 출처·키워드 (배치 SoT 아님)
├── config.example.json    # DB 설정 샘플
├── config.json            # 로컬 비밀 (gitignore — 커밋 금지)
├── templates/index.html   # 테스트 UI (GET / 로 서빙)
├── static/                # /static/style.css, /static/script.js
└── README.md              # 본 문서
```

---

## 프론트 체크리스트

- [ ] Base URL: `http://127.0.0.1:5000` (또는 배포 URL)  
- [ ] CORS 확인 (개발은 전체 허용)  
- [ ] 스펙 확인: `/docs` 또는 본 README  
- [ ] 목록: `GET /api/categories` (설정) vs `articles` (콘텐츠) 구분  
- [ ] 긴 API 는 NDJSON 파서 구현 (`response.json()` 금지)  
- [ ] `db.saved / skipped / no_content` 사용자 메시지 설계  
- [ ] 전체 저장 전 수집 가능 sources 존재 확인  
- [ ] 기사 상세 링크는 `source_url` (`link`) 사용  
- [ ] 본문 표시는 `cleaned_content` (수집 응답의 `content`)  
- [ ] secrets: `config.json` 커밋 금지  

질문·API 추가 요청(예: 페이지네이션 기사 목록, 키워드 필터)은 백엔드와 이 README 기준으로 맞추면 됩니다.
