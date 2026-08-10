import psycopg
import json
from dateutil import parser as dateutil_parser

# ── DB 설정 로드 ───────────────────────────────────────────────
def _load_db_config():
    for enc in ('utf-8', 'utf-8-sig', 'cp949', 'euc-kr'):
        try:
            with open('config.json', 'r', encoding=enc) as f:
                cfg = json.load(f)
            return cfg.get('database', {})
        except (UnicodeDecodeError, ValueError):
            continue
    raise RuntimeError("config.json 인코딩을 읽을 수 없습니다.")

def get_connection():
    """PostgreSQL 연결 반환"""
    cfg = _load_db_config()
    return psycopg.connect(
        host=cfg.get('host', 'localhost'),
        port=cfg.get('port', 5432),
        dbname=cfg.get('dbname', 'news_collect'),
        user=cfg.get('user', 'postgres'),
        password=cfg.get('password', ''),
        options='-c lc_messages=C',
    )

# ── source_type 자동 판별 ──────────────────────────────────────
_TONGSHINSA_KEYWORDS = ['연합뉴스', 'reuters', 'ap ', 'afp', 'bloomberg', 'yonhap']
_OFFICIAL_KEYWORDS   = ['who', '정부', '국토교통부', '기상청', '행정안전부', '환경부',
                        '교육부', '보건복지부', '외교부', '금융위', '한국은행']

def _detect_source_type(name: str) -> tuple[str, float]:
    """
    소스명으로 source_type과 credibility_weight 자동 결정.
    반환: (source_type, credibility_weight)
    """
    lower = name.lower()
    if any(k in lower for k in _OFFICIAL_KEYWORDS):
        return '공식발표', 0.95
    if any(k in lower for k in _TONGSHINSA_KEYWORDS):
        return '통신사', 0.90
    return '전문미디어', 0.80

# ── sources 테이블 ─────────────────────────────────────────────
def upsert_source(
    conn,
    name: str,
    rss_url: str,
    source_type: str | None = None,
    credibility_weight: float | None = None,
) -> int:
    """
    rss_url 기준으로 sources 행을 INSERT OR GET.
    source_id 반환.
    source_type / credibility_weight 미지정 시 이름 기반 자동 판별.
    """
    if source_type is None or credibility_weight is None:
        auto_type, auto_w = _detect_source_type(name)
        source_type = source_type or auto_type
        credibility_weight = credibility_weight if credibility_weight is not None else auto_w

    with conn.cursor() as cur:
        # 이미 존재하면 source_id만 반환
        cur.execute(
            "SELECT source_id FROM sources WHERE rss_url = %s",
            (rss_url,)
        )
        row = cur.fetchone()
        if row:
            return row[0]

        # 신규 삽입
        cur.execute(
            """
            INSERT INTO sources (name, rss_url, source_type, credibility_weight)
            VALUES (%s, %s, %s, %s)
            RETURNING source_id
            """,
            (name, rss_url, source_type, credibility_weight)
        )
        source_id = cur.fetchone()[0]
        conn.commit()
        return source_id


def register_google_news_origin(name: str, rss_url: str, keyword: str | None = None) -> dict:
    """
    Google News 키워드 원천 소스를 sources 에 등록.
    (파생 '언론사 - 키워드' 와 구분: 실제 news.google.com RSS URL)
    반환: { source_id, name, rss_url, keyword, created: bool }
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_id, name FROM sources WHERE rss_url = %s",
                (rss_url,),
            )
            row = cur.fetchone()
            if row:
                return {
                    'source_id': row[0],
                    'name': row[1],
                    'rss_url': rss_url,
                    'keyword': keyword,
                    'created': False,
                }

            sid = upsert_source(
                conn,
                name=name,
                rss_url=rss_url,
                source_type='포털API',
                credibility_weight=0.75,
            )
            return {
                'source_id': sid,
                'name': name,
                'rss_url': rss_url,
                'keyword': keyword,
                'created': True,
            }
    finally:
        conn.close()

# ── articles 테이블 ────────────────────────────────────────────
def _parse_published_at(pub_str: str):
    """published 문자열 → timezone-aware datetime 또는 None"""
    if not pub_str or pub_str == 'N/A':
        return None
    try:
        return dateutil_parser.parse(pub_str)
    except Exception:
        return None

def _has_valid_body(article: dict) -> bool:
    """본문 수집에 성공한 기사만 True (실패·빈 본문은 DB 저장 대상 아님)"""
    content = article.get('content')
    if content is None:
        return False
    if not isinstance(content, str):
        content = str(content)
    text = content.strip()
    if not text:
        return False
    if text == '본문을 가져올 수 없습니다.':
        return False
    return True


def insert_article(conn, source_id: int, article: dict) -> tuple[bool, str]:
    """
    단일 기사를 articles 테이블에 삽입.
    - 본문 수집 실패 기사: 저장하지 않음
    - source_url 중복이면 스킵
    반환: (삽입됨: bool, 상태메시지: str)

    article 딕셔너리 키:
        title, content, link, published, (선택) raw_content
    """
    if not _has_valid_body(article):
        return False, '본문없음'

    source_url = article.get('link', '').strip()
    if not source_url:
        return False, '링크 없음'

    title = (article.get('title') or '').strip()[:500]
    if not title:
        return False, '제목 없음'

    cleaned_content = article.get('content').strip()
    raw_content    = article.get('raw_content')
    published_at   = _parse_published_at(article.get('published', ''))

    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO articles
                    (source_id, source_url, title, cleaned_content, raw_content, published_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (source_id, source_url, title, cleaned_content, raw_content, published_at)
            )
            conn.commit()
            return True, '저장됨'
        except psycopg.errors.UniqueViolation:
            conn.rollback()
            return False, '중복'
        except Exception as e:
            conn.rollback()
            return False, f'오류: {e}'

def derived_gn_source_name(publisher: str, keyword: str) -> str:
    """
    Google News 파생 소스 표시명.
    일반 RSS '매일경제 - 경제' 와 구분하기 위해 접미 (GN) 사용.
    """
    publisher = (publisher or '').strip() or 'Unknown'
    keyword = (keyword or '').strip()
    if keyword:
        return f"{publisher} - {keyword} (GN)"
    return f"{publisher} (GN)"


def upsert_source_named(conn, name: str, rss_url: str) -> int:
    """
    name 또는 rss_url 기준으로 sources 조회 후 없으면 INSERT.
    Google News 파생 저장 시 사용.

    - google_news:// URL: rss_url 로만 조회 (이름 재사용으로 일반 RSS 와 합쳐지지 않음)
    - 그 외: rss_url 후 name 재사용 (레거시)
    """
    source_type, credibility_weight = _detect_source_type(name)
    is_gn_derived = (rss_url or '').startswith('google_news://')

    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_id FROM sources WHERE rss_url = %s",
            (rss_url,),
        )
        row = cur.fetchone()
        if row:
            # 파생 소스 이름 규칙이 바뀌었을 수 있으면 (GN) 형태로 맞춤
            if is_gn_derived and name:
                cur.execute(
                    "UPDATE sources SET name = %s WHERE source_id = %s AND name IS DISTINCT FROM %s",
                    (name, row[0], name),
                )
                conn.commit()
            return row[0]

        if not is_gn_derived:
            # 동일 이름 소스가 있으면 재사용 (rss_url 없는 레거시 대비)
            cur.execute(
                "SELECT source_id FROM sources WHERE name = %s LIMIT 1",
                (name,),
            )
            row = cur.fetchone()
            if row:
                return row[0]

        cur.execute(
            """
            INSERT INTO sources (name, rss_url, source_type, credibility_weight)
            VALUES (%s, %s, %s, %s)
            RETURNING source_id
            """,
            (name, rss_url, source_type, credibility_weight),
        )
        source_id = cur.fetchone()[0]
        conn.commit()
        return source_id


# ── 일괄 저장 (메인 진입점) ────────────────────────────────────
def save_articles_to_db(
    feed_name: str,
    rss_url: str,
    articles: list,
    google_news_keyword: str | None = None,
) -> dict:
    """
    fetch_rss_articles() 결과를 DB에 저장.
    본문 없는 기사는 저장하지 않음.

    google_news_keyword 가 있으면 기사별 언론사로
    sources.name = '{언론사} - {키워드} (GN)' 를 upsert 한 뒤 저장.

    반환: { saved, skipped, no_content, errors }
    """
    if google_news_keyword:
        return _save_google_news_articles(google_news_keyword, articles)

    saved = skipped = no_content = errors = 0
    try:
        conn = get_connection()
        try:
            source_id = upsert_source(conn, feed_name, rss_url)
            for article in articles:
                ok, msg = insert_article(conn, source_id, article)
                if ok:
                    saved += 1
                elif msg == '중복':
                    skipped += 1
                elif msg == '본문없음':
                    no_content += 1
                else:
                    errors += 1
        finally:
            conn.close()
    except Exception as e:
        return {
            'saved': 0, 'skipped': 0, 'no_content': 0,
            'errors': len(articles), 'detail': str(e),
        }

    return {
        'saved': saved,
        'skipped': skipped,
        'no_content': no_content,
        'errors': errors,
    }


def _save_google_news_articles(keyword: str, articles: list) -> dict:
    """
    Google News 기사 저장.
    각 기사 publisher 로 sources 를 '언론사 - 키워드 (GN)' 형태로 분리 저장.
    일반 RSS '언론사 - 섹션' 과 이름이 겹치지 않도록 (GN) 접미 사용.
    """
    keyword = (keyword or '').strip()
    saved = skipped = no_content = errors = 0
    try:
        conn = get_connection()
        try:
            for article in articles:
                publisher = (article.get('publisher') or '').strip() or 'Unknown'
                source_name = derived_gn_source_name(publisher, keyword)
                # UNIQUE rss_url 용 synthetic key (전체 저장 수집 대상에서 제외)
                rss_key = f"google_news://{keyword}/{publisher}"
                try:
                    source_id = upsert_source_named(conn, source_name, rss_key)
                except Exception:
                    errors += 1
                    continue

                ok, msg = insert_article(conn, source_id, article)
                if ok:
                    saved += 1
                elif msg == '중복':
                    skipped += 1
                elif msg == '본문없음':
                    no_content += 1
                else:
                    errors += 1
        finally:
            conn.close()
    except Exception as e:
        return {
            'saved': 0, 'skipped': 0, 'no_content': 0,
            'errors': len(articles), 'detail': str(e),
        }

    return {
        'saved': saved,
        'skipped': skipped,
        'no_content': no_content,
        'errors': errors,
    }

def list_collectible_sources() -> list[dict]:
    """
    전체 DB 저장 대상 sources.
    - 실제 HTTP(S) RSS URL 만 포함 (Google News 원천 키워드 RSS 포함)
    - 파생 소스 제외:
        · rss_url LIKE 'google_news://%'
        · name 이 ' (GN)' 으로 끝남
      → 파생 소스는 GN 키워드 수집 시 article 적재용이며 재수집하지 않음
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    """
                    SELECT source_id, name, rss_url, source_type, credibility_weight
                    FROM sources
                    WHERE rss_url IS NOT NULL
                      AND rss_url <> ''
                      AND rss_url NOT LIKE 'google_news://%%'
                      AND name NOT LIKE '%% (GN)'
                      AND (
                            rss_url LIKE 'http://%%'
                         OR rss_url LIKE 'https://%%'
                      )
                    ORDER BY source_id
                    """
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        raise RuntimeError(f'sources 조회 실패: {e}') from e


def migrate_gn_derived_source_names() -> dict:
    """
    기존 파생 소스 이름을 '… (GN)' 규칙으로 일괄 보정.
    - rss_url 이 google_news:// 인데 name 이 (GN) 으로 안 끝나면 접미 추가
    """
    conn = get_connection()
    try:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                SELECT source_id, name, rss_url
                FROM sources
                WHERE rss_url LIKE 'google_news://%%'
                ORDER BY source_id
                """
            )
            rows = [dict(r) for r in cur.fetchall()]
            updated = []
            for r in rows:
                old = r['name'] or ''
                if old.endswith(' (GN)'):
                    continue
                # google_news://keyword/publisher → 표준 이름 재생성 시도
                path = (r['rss_url'] or '').replace('google_news://', '', 1)
                if '/' in path:
                    keyword, publisher = path.split('/', 1)
                    new_name = derived_gn_source_name(publisher, keyword)
                else:
                    new_name = old if old.endswith(' (GN)') else f'{old} (GN)'
                if new_name != old:
                    cur.execute(
                        "UPDATE sources SET name = %s WHERE source_id = %s",
                        (new_name, r['source_id']),
                    )
                    updated.append({
                        'source_id': r['source_id'],
                        'old': old,
                        'new': new_name,
                    })
            conn.commit()
            return {'scanned': len(rows), 'updated': len(updated), 'changes': updated}
    finally:
        conn.close()


# ── 간단 통계 조회 ─────────────────────────────────────────────
def get_db_stats() -> dict:
    """sources / articles 건수 조회"""
    try:
        conn = get_connection()
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM sources")
            sources_count = cur.fetchone()['cnt']

            cur.execute("SELECT COUNT(*) AS cnt FROM articles")
            articles_count = cur.fetchone()['cnt']

            cur.execute(
                """
                SELECT s.name, COUNT(a.article_id) AS article_count
                FROM sources s
                LEFT JOIN articles a ON a.source_id = s.source_id
                GROUP BY s.source_id, s.name
                ORDER BY article_count DESC
                LIMIT 10
                """
            )
            top_sources = [dict(r) for r in cur.fetchall()]
        conn.close()
        return {
            'success': True,
            'sources_count': sources_count,
            'articles_count': articles_count,
            'top_sources': top_sources,
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}
