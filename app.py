from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import feedparser
import requests
import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional
import urllib3
from urllib.parse import urlparse, quote, unquote, parse_qs
from datetime import datetime
from dateutil import parser as dateutil_parser
from bs4 import BeautifulSoup
import db

# SSL 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title='news_collect',
    description='RSS / Google News 수집 · 본문 추출 · PostgreSQL 적재 API',
    version='1.0.0',
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')

REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

# 도메인별 추가 헤더 (requests 전용 — curl_cffi는 자체 헤더 사용)
_DOMAIN_HEADERS = {
    'hankyung.com': {'Referer': 'https://www.hankyung.com/'},
    'chosun.com':   {'Referer': 'https://www.chosun.com/'},
    'mk.co.kr':     {'Referer': 'https://www.mk.co.kr/'},
    'yna.co.kr':    {'Referer': 'https://www.yna.co.kr/'},
}

# Cloudflare 대응: 최신 Chrome 프로필을 먼저 시도
# (한국경제 RSS는 chrome124 이하에서 403, chrome136+ 에서 통과)
_CF_IMPERSONATE_LIST = [
    'chrome136', 'chrome142', 'chrome133a', 'chrome131',
    'chrome124', 'chrome120', 'chrome116', 'edge101',
]

# Cloudflare 보호 도메인 — 최신 프로필 우선 + 홈페이지 쿠키 워밍업
_CF_PROTECTED_DOMAINS = ('hankyung.com',)


def _get_headers(url: str) -> dict:
    headers = dict(REQUEST_HEADERS)
    for domain, extra in _DOMAIN_HEADERS.items():
        if domain in url:
            headers.update(extra)
            break
    return headers


def _is_challenge_page(content: bytes, status_code: int) -> bool:
    """Cloudflare 등 봇 챌린지 페이지 여부"""
    if status_code in (403, 503, 429):
        return True
    if not content:
        return False
    head = content[:2000].lower()
    return (
        b'just a moment' in head
        or b'cf-browser-verification' in head
        or b'challenge-platform' in head
        or b'attention required' in head
    )


def _smart_get(url: str, timeout: int = 20):
    """
    최강 요청 함수:
    1차: curl_cffi impersonate — 헤더 주입 없이 완전한 브라우저 핑거프린트
         (User-Agent/Sec-* 헤더를 직접 주면 핑거프린트가 깨져서 오히려 역효과)
    2차: Cloudflare 보호 사이트는 홈페이지 세션 워밍업 후 재시도
    3차: requests fallback
    """
    host = urlparse(url).netloc.lower()
    needs_cf = any(d in host for d in _CF_PROTECTED_DOMAINS)

    try:
        from curl_cffi import requests as cf

        # 일반 시도 (최신 프로필 우선)
        for version in _CF_IMPERSONATE_LIST:
            try:
                r = cf.get(url, impersonate=version, timeout=timeout)
                if r.status_code < 400 and not _is_challenge_page(r.content, r.status_code):
                    return r
            except Exception:
                continue

        # Cloudflare 보호 도메인: 홈페이지 방문으로 쿠키 확보 후 재시도
        if needs_cf:
            origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            for version in _CF_IMPERSONATE_LIST[:4]:
                try:
                    session = cf.Session(impersonate=version)
                    session.get(origin + '/', timeout=timeout)
                    r = session.get(url, timeout=timeout)
                    if r.status_code < 400 and not _is_challenge_page(r.content, r.status_code):
                        return r
                except Exception:
                    continue
    except ImportError:
        pass

    # requests fallback
    return requests.get(url, headers=_get_headers(url), verify=False, timeout=timeout)


def _decode_response(r) -> str:
    """응답 본문을 올바른 인코딩으로 디코드"""
    content_type = getattr(r, 'headers', {}).get('content-type', '')
    if 'charset=' in content_type:
        enc = content_type.split('charset=')[-1].strip().split(';')[0]
        try:
            return r.content.decode(enc)
        except Exception:
            pass
    try:
        import chardet
        detected = chardet.detect(r.content[:4096])
        enc = detected.get('encoding') or 'utf-8'
        return r.content.decode(enc, errors='replace')
    except Exception:
        pass
    return r.content.decode('utf-8', errors='replace')


def _clean_text(text: str) -> str:
    """공백 정리된 본문 텍스트"""
    if not text:
        return ''
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return '\n'.join(lines)


def _html_to_text(html_fragment: str) -> str:
    if not html_fragment:
        return ''
    return BeautifulSoup(html_fragment, 'html.parser').get_text(' ', strip=True)


def _parse_fusion_global_content(html: str) -> dict | None:
    """
    조선일보(ARC Publishing Fusion) 페이지에서 Fusion.globalContent JSON 파싱.
    본문이 DOM이 아니라 JS 변수에만 들어 있음.
    """
    marker = 'Fusion.globalContent='
    start = html.find(marker)
    if start < 0:
        marker = 'Fusion.globalContent ='
        start = html.find(marker)
    if start < 0:
        return None
    brace = html.find('{', start)
    if brace < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    quote = ''
    for i in range(brace, len(html)):
        ch = html[i]
        if in_str:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                raw = html[brace:i + 1]
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return None
    return None


def _extract_chosun_body(html: str) -> str | None:
    """조선일보: Fusion.globalContent.content_elements 에서 본문 조립"""
    data = _parse_fusion_global_content(html)
    if not data:
        return None

    parts = []
    for el in data.get('content_elements') or []:
        t = el.get('type')
        if t in ('text', 'header', 'raw_html'):
            content = _html_to_text(el.get('content') or '')
            if content:
                parts.append(content)
        elif t == 'list':
            for item in el.get('items') or []:
                content = _html_to_text(item.get('content') or '')
                if content:
                    parts.append(content)
        elif t == 'quote':
            content = _html_to_text(el.get('content') or el.get('citation') or '')
            if content:
                parts.append(content)
        elif t == 'image':
            # 이미지 기사는 캡션이라도 확보
            caption = _html_to_text(el.get('caption') or el.get('subtitle') or '')
            if caption:
                parts.append(caption)

    text = _clean_text('\n\n'.join(parts))
    if len(text) > 80:
        return text

    # 짧은 인사/속보 등: 제목·요약과 합쳐 최소 본문 확보
    headline = ''
    if isinstance(data.get('headlines'), dict):
        headline = (data['headlines'].get('basic') or '').strip()
    desc = ''
    if isinstance(data.get('description'), dict):
        desc = (data['description'].get('basic') or '').strip()
    combined = _clean_text('\n\n'.join(x for x in (headline, desc, text) if x))
    return combined if len(combined) > 30 else None


def _extract_hankyung_body(html: str) -> str | None:
    """한국경제: .article-body 우선, 페이월 영역 제거"""
    soup = BeautifulSoup(html, 'html.parser')
    for junk in soup.select(
        '.paywall, .paywall__body, .paywall__contents, .paywall-popup, '
        '.article-utility, .article-byline-wrap, script, style, noscript'
    ):
        junk.decompose()

    body = soup.select_one('.article-body') or soup.select_one('.article-body-wrap')
    if not body:
        return None

    # p 태그 위주 추출 (광고/버튼 노이즈 감소)
    paragraphs = body.find_all(['p', 'h2', 'h3'])
    if paragraphs:
        text = '\n\n'.join(
            p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
        )
    else:
        text = body.get_text(separator='\n', strip=True)

    text = _clean_text(text)
    return text if len(text) > 80 else None


def _looks_like_site_footer(text: str) -> bool:
    """
    Readability가 기사 대신 언론사 푸터(주소·등록번호)를 본문으로 고르는 경우 걸러냄.
    동아일보 등에서 약 137자 푸터가 '성공'으로 잡히던 문제 대응.
    """
    if not text:
        return True
    markers = ('등록번호', '발행·편집인', '발행일자', '등록일자', '서울아00', '전화번호')
    hits = sum(1 for m in markers if m in text)
    if hits >= 2 and len(text) < 400:
        return True
    # "동아일보\n주소 서울..." 형태
    if '동아일보' in text[:30] and '주소' in text and len(text) < 300:
        return True
    return False


def _looks_like_truncated(text: str) -> bool:
    """
    본문이 중간에서 잘린 것처럼 보이면 True.
    GeekNews 등은 JSON-LD articleBody를 ~1800자로 잘라 '...' 로 끝냄.
    """
    if not text:
        return True
    t = text.rstrip()
    return t.endswith('...') or t.endswith('…')


def _looks_like_ai_summary(text: str) -> bool:
    """
    매일경제 등 'AI 요약/핵심요약 쏙' 블록이 본문으로 잡힌 경우 감지.
    원문이 아니라 OpenAI 요약·Key Points 스타일 텍스트.
    """
    if not text:
        return True
    head = text[:400]
    markers = (
        'Key Points',
        'AI 요약은 OpenAI',
        'AI 요약은 OpenAI의',
        '핵심요약 쏙',
        '전체 맥락을 이해하려면 기사 본문을',
        'OpenAI의 최신 기술을 활용해',
        'Powered by perplexity',
    )
    if any(m in text for m in markers):
        return True
    # "했어요/네요" 구어체 + 이모지가 많은 AI 요약 톤 (원문 기사체와 다름)
    if head.lstrip().startswith('Key Points'):
        return True
    emoji_hits = sum(1 for ch in head if ord(ch) > 0x1F300)
    if emoji_hits >= 2 and ('했어요' in head or '네요' in head or '거예요' in head):
        return True
    return False


def _strip_ai_summary_nodes(soup: BeautifulSoup) -> None:
    """페이지에 붙은 AI 요약 모달/위젯 제거 (매일경제 핵심요약 쏙 등)"""
    selectors = (
        '.modal_ai_explain',
        '.ai_explain_wrap',
        '.ai_explain_body',
        '.ai_explain_head',
        '.keypoints_section',
        '.keypoints_list',
        '.keypoints_item',
        '.list_ai_ask',
        '.ai_question',
        '.ai_logo_wrap_s',
        '.ai_right_btn',
        '.news_summary_bg',
        '[class*="ai_explain"]',
        '[class*="keypoints"]',
    )
    for sel in selectors:
        for node in soup.select(sel):
            node.decompose()


def _extract_mk_body(html: str) -> str | None:
    """
    매일경제(mk.co.kr):
    - 실제 본문: .news_cnt_detail_wrap / [itemprop=articleBody]
    - 같은 HTML에 OpenAI '핵심요약 쏙' 모달(.ai_explain_*)이 있어
      Readability가 요약문을 본문으로 오인하는 문제 대응
    """
    soup = BeautifulSoup(html, 'html.parser')
    _strip_ai_summary_nodes(soup)

    body = (
        soup.select_one('.news_cnt_detail_wrap')
        or soup.select_one('[itemprop="articleBody"]')
        or soup.select_one('#article_body')
        or soup.select_one('.art_txt')
    )
    if not body:
        return None

    for junk in body.select(
        'script, style, noscript, iframe, '
        '.thumb_area, .thumb, .ad, .mid_title, button, .img_desc'
    ):
        junk.decompose()

    for br in body.find_all('br'):
        br.replace_with('\n')

    paragraphs = body.find_all('p')
    if paragraphs:
        text = '\n\n'.join(
            p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
        )
    else:
        text = body.get_text(separator='\n', strip=True)

    text = _clean_text(text)
    if _looks_like_ai_summary(text) or _looks_like_site_footer(text):
        return None
    return text if len(text) > 80 else None


def _extract_geeknews_body(html: str) -> str | None:
    """
    GeekNews (news.hada.io):
    - 전체 본문: section.article-content#topic_contents / .topic_contents
    - JSON-LD articleBody 는 약 1800자에서 '...' 으로 잘림 → 사용 금지
    - 댓글·관련토픽 제외
    """
    soup = BeautifulSoup(html, 'html.parser')
    for junk in soup.select(
        'script, style, noscript, iframe, '
        '.comment, .comments, #comments, .related-topics, '
        'form, .vote, .topictitle'
    ):
        junk.decompose()

    body = (
        soup.select_one('section.article-content#topic_contents')
        or soup.select_one('#topic_contents')
        or soup.select_one('.topic_contents')
        or soup.select_one('section.article-content')
        or soup.select_one('.article-content')
    )
    if not body:
        return None

    for br in body.find_all('br'):
        br.replace_with('\n')

    # 불릿 본문이면 항목별로 문단 구성
    items = body.find_all('li')
    if items:
        parts = [li.get_text(' ', strip=True) for li in items if li.get_text(strip=True)]
        text = '\n\n'.join(parts)
    else:
        text = body.get_text(separator='\n', strip=True)

    text = _clean_text(text)
    if _looks_like_truncated(text) or _looks_like_site_footer(text):
        return None
    return text if len(text) > 40 else None


def _extract_donga_body(html: str) -> str | None:
    """
    동아일보: section.news_view
    - 본문이 <p>가 아니라 텍스트 노드 + <br><br> 로 들어 있음
    - Readability는 종종 회사 정보 푸터를 본문으로 오인함
    """
    soup = BeautifulSoup(html, 'html.parser')
    node = soup.select_one('section.news_view') or soup.select_one('.news_view')
    if not node:
        # 스포츠동아 등 변형
        node = (
            soup.select_one('#article_txt')
            or soup.select_one('.article_txt')
            or soup.select_one('.news_view_wrap')
        )
    if not node:
        return None

    # 광고·스크립트 제거
    for junk in node.select(
        'script, style, noscript, iframe, '
        '.view_adK, .view_m_adK, .view_ad06, .view_m_adA, .view_ad07, '
        '.ad, .box.bg, .a1, [class*="view_ad"], [class*="view_m_ad"]'
    ):
        junk.decompose()

    # <br> → 줄바꿈 (동아 본문 단락 구분)
    for br in node.find_all('br'):
        br.replace_with('\n')

    text = _clean_text(node.get_text(separator='\n', strip=True))
    if _looks_like_site_footer(text):
        return None
    return text if len(text) > 80 else None


def _extract_jsonld_body(html: str) -> str | None:
    """schema.org NewsArticle articleBody"""
    soup = BeautifulSoup(html, 'html.parser')
    for s in soup.find_all('script', type='application/ld+json'):
        raw = s.string or s.get_text() or ''
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            # @graph 지원
            graph = item.get('@graph')
            if isinstance(graph, list):
                items.extend(graph)
            ab = item.get('articleBody')
            if ab and len(ab.strip()) > 100:
                return _clean_text(ab)
    return None


def _extract_site_specific(url: str, html: str) -> tuple[str | None, str | None]:
    """
    도메인별 전용 추출기.
    반환: (content, method_name) 또는 (None, None)
    """
    host = urlparse(url).netloc.lower()

    if 'chosun.com' in host:
        text = _extract_chosun_body(html)
        if text:
            return text, 'ChosunFusion'

    if 'hankyung.com' in host:
        text = _extract_hankyung_body(html)
        if text:
            return text, 'HankyungBody'

    # www.donga.com / sports.donga.com / m.donga.com
    if 'donga.com' in host:
        text = _extract_donga_body(html)
        if text:
            return text, 'DongaBody'

    # 매일경제 — AI 요약 모달 제외한 원문
    if 'mk.co.kr' in host:
        text = _extract_mk_body(html)
        if text:
            return text, 'MkBody'

    # GeekNews — JSON-LD 잘림 대신 페이지 본문
    if 'news.hada.io' in host or 'hada.io' in host:
        text = _extract_geeknews_body(html)
        if text:
            return text, 'GeekNewsBody'

    return None, None


def _fetch_feed(url: str):
    """
    RSS 피드 파싱
    1차: curl_cffi Chrome impersonation (Cloudflare 대응 최신 프로필)
    2차: feedparser 직접
    """
    try:
        r = _smart_get(url, timeout=20)
        if r is not None and getattr(r, 'status_code', 0) == 200:
            if _is_challenge_page(r.content, r.status_code):
                pass
            else:
                feed = feedparser.parse(r.content)
                if feed.entries:
                    return feed
    except Exception:
        pass

    try:
        feed = feedparser.parse(url)
        if feed.entries:
            return feed
    except Exception:
        pass

    return None


def _extract_from_entry(entry) -> str | None:
    """
    RSS entry에 포함된 본문을 추출 (TechCrunch, BBC 등 full-text RSS 지원 사이트용)
    HTML 태그 제거 후 순수 텍스트 반환. 200자 미만이면 None 반환(요약만 있는 경우).
    """
    raw = ''
    if entry.get('content'):
        raw = entry.content[0].get('value', '')
    elif entry.get('summary'):
        raw = entry.get('summary', '')

    if not raw:
        return None

    soup = BeautifulSoup(raw, 'html.parser')
    text = _clean_text(soup.get_text(separator='\n', strip=True))
    return text if len(text) > 200 else None


def extract_article_body(url):
    """
    기사 본문 추출 파이프라인:
    0차: 도메인 전용 추출 (조선 Fusion / 한경 article-body)
    1차: readability-lxml
    2차: JSON-LD articleBody
    3차: BeautifulSoup 셀렉터
    Returns: (content, method, raw_html)
    """
    try:
        resp = _smart_get(url, timeout=20)
        if resp is None:
            return None, "실패", None

        raw_html = _decode_response(resp)
        if not raw_html or _is_challenge_page(resp.content, getattr(resp, 'status_code', 0)):
            return None, "실패", raw_html

        # 0차: 사이트 전용
        site_text, site_method = _extract_site_specific(url, raw_html)
        if site_text:
            return site_text, site_method, raw_html

        # 공통: AI 요약 위젯 제거 후 파싱 (매일경제 핵심요약 쏙 등)
        soup_clean = BeautifulSoup(raw_html, 'html.parser')
        _strip_ai_summary_nodes(soup_clean)
        clean_html = str(soup_clean)

        # 1차: readability-lxml (푸터·AI 요약 오탐 제외)
        try:
            from readability import Document
            doc = Document(clean_html)
            soup_r = BeautifulSoup(doc.summary(), 'html.parser')
            content = _clean_text(soup_r.get_text(separator='\n', strip=True))
            if (
                content and len(content) > 100
                and not _looks_like_site_footer(content)
                and not _looks_like_ai_summary(content)
                and not _looks_like_truncated(content)
            ):
                return content, "Readability", raw_html
        except Exception:
            pass

        # 2차: JSON-LD (잘린 articleBody 제외 — GeekNews 등)
        jsonld = _extract_jsonld_body(raw_html)
        if (
            jsonld and not _looks_like_site_footer(jsonld)
            and not _looks_like_ai_summary(jsonld)
            and not _looks_like_truncated(jsonld)
        ):
            return jsonld, "JSON-LD", raw_html

        # 3차: BeautifulSoup fallback
        soup = BeautifulSoup(clean_html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header']):
            tag.decompose()

        # 명시적 셀렉터 우선 (동아 news_view: p 없이 br 본문)
        for css in (
            'section.news_view', '.news_view',
            '.news_cnt_detail_wrap', '[itemprop="articleBody"]',
            '.article-body', '.article-body-wrap',
            '#article-body', '#article-view-content-div',
            '#article_txt', '.article_txt',
            'article .content', 'article',
        ):
            node = soup.select_one(css)
            if node:
                for br in node.find_all('br'):
                    br.replace_with('\n')
                paragraphs = node.find_all('p')
                if paragraphs:
                    text = '\n\n'.join(
                        p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
                    )
                else:
                    text = node.get_text(separator='\n', strip=True)
                text = _clean_text(text)
                if (
                    text and len(text) > 100
                    and not _looks_like_site_footer(text)
                    and not _looks_like_ai_summary(text)
                    and not _looks_like_truncated(text)
                ):
                    return text, "BeautifulSoup", raw_html

        article_content = None
        selectors = [
            {'class': lambda x: x and 'article' in ' '.join(x if isinstance(x, list) else [x]).lower()},
            {'class': lambda x: x and 'content' in ' '.join(x if isinstance(x, list) else [x]).lower()},
            {'class': lambda x: x and 'body'    in ' '.join(x if isinstance(x, list) else [x]).lower()},
            {'id': lambda x: x and 'article' in x.lower()},
            {'id': lambda x: x and 'content' in x.lower()},
        ]
        for selector in selectors:
            article_content = soup.find(['article', 'div', 'main', 'section'], selector)
            if article_content:
                break
        if not article_content:
            article_content = soup.find('body')

        if article_content:
            paragraphs = article_content.find_all('p')
            text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            text = _clean_text(text)
            if text and len(text) > 100:
                return text, "BeautifulSoup", raw_html

        return None, "실패", raw_html

    except Exception:
        return None, "실패", None

# 카테고리 로드
def load_categories():
    with open('categories.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def save_categories(categories: dict):
    with open('categories.json', 'w', encoding='utf-8') as f:
        json.dump(categories, f, ensure_ascii=False, indent=2)


def build_google_news_rss_url(keyword: str) -> str:
    """키워드 → Google News 검색 RSS URL (한국)"""
    q = quote(keyword.strip())
    return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"


def is_google_news_origin_url(url: str) -> bool:
    """실제 Google News 검색 RSS (파생 google_news:// 제외)"""
    u = (url or '').lower()
    return 'news.google.com' in u and u.startswith('http')


def keyword_from_google_news_source(name: str, rss_url: str, keyword: str | None = None) -> str:
    """sources 행에서 GN 키워드 복원"""
    if keyword and str(keyword).strip():
        return str(keyword).strip()
    # name: "Google News · 증권"
    if name and '·' in name:
        return name.split('·', 1)[1].strip()
    if name and ' - ' in name and name.lower().startswith('google'):
        return name.split(' - ', 1)[1].strip()
    # URL q=
    try:
        q = parse_qs(urlparse(rss_url).query).get('q', [''])[0]
        if q:
            return unquote(q)
    except Exception:
        pass
    return ''


# Google News URL 해석 캐시 (동일 세션 내 재요청 가속)
_GN_URL_CACHE: dict[str, str] = {}
_GN_URL_CACHE_LOCK = threading.Lock()

# 기사 본문 병렬 수집 워커 수 (Google News decode+HTTP 가 병목)
_ARTICLE_WORKERS = 8
# 전체 DB 저장 시 피드(출처) 병렬 수 — 피드×기사 중첩 스레드 폭주 방지
_FEED_WORKERS = 4
# 전체 저장 중 피드당 기사 워커 (FEED_WORKERS × 이 값 ≈ 동시 HTTP 상한)
_ARTICLE_WORKERS_IN_BATCH = 4


def resolve_google_news_url(url: str) -> str:
    """Google News 리다이렉트 URL → 원문 기사 URL (캐시 포함)"""
    if not url or 'news.google.com' not in url:
        return url
    with _GN_URL_CACHE_LOCK:
        cached = _GN_URL_CACHE.get(url)
    if cached:
        return cached
    decoded = url
    try:
        from googlenewsdecoder import new_decoderv1
        result = new_decoderv1(url)
        if isinstance(result, dict) and result.get('status') and result.get('decoded_url'):
            decoded = result['decoded_url']
    except Exception:
        pass
    with _GN_URL_CACHE_LOCK:
        _GN_URL_CACHE[url] = decoded
    return decoded


def _entry_publisher(entry) -> str:
    """RSS entry 에서 언론사명 추출 (Google News source 필드)"""
    src = entry.get('source')
    if isinstance(src, dict):
        title = (src.get('title') or '').strip()
        if title:
            return title
    # feedparser 가 객체로 줄 때
    if src is not None and hasattr(src, 'get'):
        title = (src.get('title') or '').strip()
        if title:
            return title
    if src is not None and hasattr(src, 'title'):
        title = (getattr(src, 'title') or '').strip()
        if title:
            return title
    return ''


def _looks_like_domain_publisher(publisher: str) -> bool:
    """
    Google News source.title 이 브랜드명이 아닌 호스트/도메인 형태인지.
    예: v.daum.net, spnews.co.kr, imnews.imbc.com
    """
    p = (publisher or '').strip()
    if not p:
        return False
    low = p.lower()
    if low.startswith('http://') or low.startswith('https://'):
        try:
            p = urlparse(p).netloc or p
        except Exception:
            pass
    p = p.strip().lower().rstrip('/')
    if not p or ' ' in p or '/' in p:
        return False
    if '.' not in p:
        return False
    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789.-')
    if not all(c in allowed for c in p):
        return False
    if p.startswith('.') or p.endswith('.') or '..' in p:
        return False
    labels = p.split('.')
    if len(labels) < 2:
        return False
    tld = labels[-1]
    if not tld.isalpha() or len(tld) < 2:
        return False
    return True


def _extract_og_site_name(html: str | None) -> str:
    """HTML 메타 og:site_name 추출"""
    if not html:
        return ''
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for attrs in (
            {'property': lambda v: v and str(v).lower() == 'og:site_name'},
            {'name': lambda v: v and str(v).lower() == 'og:site_name'},
        ):
            tag = soup.find('meta', attrs=attrs)
            if tag:
                content = (tag.get('content') or '').strip()
                if content:
                    return content
    except Exception:
        pass
    return ''


# 포털 신디케이션 og:site_name 앞쪽 표기 (Daum | 매일경제 → 매일경제)
_PORTAL_SITE_PREFIXES = frozenset({
    'daum', '다음', '다음뉴스', 'daum news', '다음 뉴스',
    'naver', '네이버', '네이버뉴스', 'naver news', '네이버 뉴스',
    'kakao', '카카오', '카카오뉴스',
})


def _normalize_og_site_name(site_name: str) -> str:
    """
    og:site_name 정규화.
    - 'Daum | 매일경제' → '매일경제'
    - 'MBC 뉴스' 그대로
    """
    s = (site_name or '').strip()
    if not s:
        return ''
    for sep in ('|', '｜', '·'):
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if len(parts) >= 2:
                for part in reversed(parts):
                    if part.lower() not in _PORTAL_SITE_PREFIXES:
                        return part
                return parts[-1]
    # 'Daum - 조선일보' 형태 (구분자 양옆 공백)
    if ' - ' in s:
        left, right = s.split(' - ', 1)
        left, right = left.strip(), right.strip()
        if left.lower() in _PORTAL_SITE_PREFIXES and right:
            return right
    return s


def _refine_publisher_from_html(publisher: str, raw_html: str | None) -> str:
    """
    도메인형 publisher 이면 본문 HTML 의 og:site_name 으로 보강.
    이미 브랜드명이거나 HTML/메타가 없으면 원본 유지.
    """
    pub = (publisher or '').strip()
    if pub and not _looks_like_domain_publisher(pub):
        return pub
    site = _normalize_og_site_name(_extract_og_site_name(raw_html))
    if not site:
        return pub
    # og 값 자체가 또 도메인이면 이득 없음
    if _looks_like_domain_publisher(site):
        return pub or site
    return site


def _clean_google_news_title(title: str, publisher: str) -> str:
    """제목 끝의 ' - 언론사' 접미 제거"""
    if not title:
        return title
    t = title.strip()
    if publisher and t.endswith(f' - {publisher}'):
        return t[: -(len(publisher) + 3)].strip()
    if ' - ' in t:
        left, right = t.rsplit(' - ', 1)
        if publisher and (right == publisher or publisher in right):
            return left.strip()
    return t


def _entry_local_date(entry):
    """
    RSS entry 발행일을 로컬(한국) 달력 날짜로 변환.
    TechCrunch 등 UTC(+0000) 피드는 .date()만 쓰면
    한국 '오늘' 기사가 UTC '어제'로 떨어져 필터에서 누락됨.
    """
    from datetime import timezone as _tz

    pub_date_str = entry.get('published') or entry.get('updated') or ''
    if pub_date_str:
        try:
            pub_dt = dateutil_parser.parse(pub_date_str)
            if pub_dt.tzinfo is not None:
                return pub_dt.astimezone().date()
            return pub_dt.date()
        except Exception:
            pass

    # feedparser struct_time (보통 UTC)
    pp = entry.get('published_parsed') or entry.get('updated_parsed')
    if pp:
        try:
            pub_dt = datetime(*pp[:6], tzinfo=_tz.utc)
            return pub_dt.astimezone().date()
        except Exception:
            pass
    return None


def _collect_one_entry(entry, is_google: bool, keyword: str | None) -> dict | None:
    """
    단일 RSS entry → 기사 dict.
    Google News: URL 해석 + 본문 추출 (스레드 풀에서 병렬 호출).
    raw_content 에 원문 HTML 저장 (DB articles.raw_content).
    도메인형 publisher 는 og:site_name 으로 보강.
    """
    publisher = _entry_publisher(entry) if is_google else ''
    raw_title = entry.get('title', 'N/A') or 'N/A'
    # 제목 접미 제거는 Google이 준 source.title(도메인 포함) 기준으로 먼저 수행
    title = _clean_google_news_title(raw_title, publisher) if is_google else raw_title

    article_url = entry.get('link', '') or ''
    if is_google and article_url:
        article_url = resolve_google_news_url(article_url)

    extraction_method = '실패'
    article_content = None
    raw_html = None
    try:
        article_content, extraction_method, raw_html = extract_article_body(article_url)
    except Exception:
        article_content = None
        extraction_method = '실패'
        raw_html = None

    if is_google and raw_html:
        publisher = _refine_publisher_from_html(publisher, raw_html)

    return {
        'title': title,
        'content': article_content if article_content else None,
        'raw_content': raw_html,
        'link': article_url,
        'published': entry.get('published') or entry.get('updated') or 'N/A',
        'method': extraction_method,
        'publisher': publisher or None,
        'keyword': keyword if is_google else None,
    }


def fetch_rss_articles(
    url,
    limit=None,
    include_yesterday=False,
    source_type: str = 'RSS',
    keyword: str | None = None,
    article_workers: int | None = None,
    progress_cb=None,
    progress_label: str | None = None,
):
    """RSS 피드에서 기사 가져오기
    include_yesterday=True 이면 오늘 + 어제 기사 모두 반환
    (날짜는 로컬 타임존 기준)

    progress_cb(message, **kwargs): 진행 상황 콜백 (선택)
    progress_label: 로그에 표시할 출처명
    """
    is_google = (source_type or '').upper() in ('GOOGLE_NEWS', 'GOOGLENEWS', 'GN')
    label = progress_label or keyword or '피드'

    def _p(msg, **kw):
        if progress_cb:
            try:
                progress_cb(msg, **kw)
            except Exception:
                pass

    try:
        _p(f'{label} · RSS 불러오는 중…', phase='fetch_rss', feed=label)
        feed = _fetch_feed(url)
        if not feed or not feed.entries:
            return {'success': False, 'error': 'RSS 피드를 가져올 수 없습니다.'}

        from datetime import timedelta
        today     = datetime.now().date()
        yesterday = today - timedelta(days=1)
        allowed_dates = {today, yesterday} if include_yesterday else {today}

        entries = feed.entries
        if limit:
            entries = entries[: int(limit)]

        candidates = []
        for entry in entries:
            pub_date = _entry_local_date(entry)
            if pub_date is None or pub_date not in allowed_dates:
                continue
            candidates.append(entry)

        total = len(candidates)
        _p(
            f'{label} · 대상 {total}건 본문 수집 시작…' if total else f'{label} · 해당 기간 기사 없음',
            phase='collect_start',
            feed=label,
            total=total,
        )

        max_workers = article_workers if article_workers is not None else _ARTICLE_WORKERS
        max_workers = max(1, int(max_workers))

        articles = []
        done_lock = threading.Lock()
        done_count = [0]

        def _work(entry):
            art = _collect_one_entry(entry, is_google, keyword)
            with done_lock:
                done_count[0] += 1
                n = done_count[0]
                # 시작·중간·끝 위주로 알림 (과도한 이벤트 방지)
                step = max(1, total // 8) if total else 1
                if n == 1 or n == total or n % step == 0:
                    _p(
                        f'{label} · 수집 중… {n}/{total}건',
                        phase='collecting',
                        feed=label,
                        current=n,
                        total=total,
                    )
            return art

        if not candidates:
            pass
        elif len(candidates) == 1:
            art = _work(candidates[0])
            if art:
                articles.append(art)
        else:
            workers = min(max_workers, len(candidates))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_work, entry) for entry in candidates]
                for fut in futures:
                    try:
                        art = fut.result()
                        if art:
                            articles.append(art)
                    except Exception:
                        continue

        failed = sum(1 for a in articles if not a['content'])
        for a in articles:
            if not a['content']:
                a['content'] = '본문을 가져올 수 없습니다.'

        ok_n = len(articles) - failed
        _p(
            f'{label} · 수집 완료 {len(articles)}건 (본문 성공 {ok_n} · 실패 {failed})',
            phase='collect_done',
            feed=label,
            total=len(articles),
            failed=failed,
        )

        return {
            'success': True,
            'title': feed.feed.get('title', 'Unknown'),
            'articles': articles,
            'count': len(feed.entries),
            'today_articles': len(articles),
            'failed': failed,
            'is_google_news': is_google,
            'keyword': keyword if is_google else None,
        }

    except Exception as e:
        _p(f'{label} · 수집 오류: {e}', phase='error', feed=label)
        return {'success': False, 'error': str(e)}


def _process_one_source_for_save(
    source: dict,
    article_workers: int | None = None,
    progress_cb=None,
) -> dict:
    """
    DB sources 한 건 수집+저장 (전체 저장 병렬 작업 단위).
    Google News 파생 소스(google_news://)는 호출 전에 이미 제외됨.
    """
    name = source.get('name') or 'Unknown'
    rss_url = source.get('rss_url') or ''
    source_id = source.get('source_id')
    source_type = source.get('source_type') or ''

    def _p(msg, **kwarg):
        if progress_cb:
            try:
                progress_cb(msg, **kwarg)
            except Exception:
                pass

    try:
        _p(
            f'{name} · 수집 시작 (source_id={source_id})',
            phase='feed_start',
            feed=name,
            source_id=source_id,
        )
        # Google News 원천(키워드 RSS) vs 일반 언론사 RSS
        is_gn_origin = is_google_news_origin_url(rss_url)
        gn_keyword = keyword_from_google_news_source(name, rss_url) if is_gn_origin else None
        result = fetch_rss_articles(
            rss_url,
            source_type='GOOGLE_NEWS' if is_gn_origin else 'RSS',
            keyword=gn_keyword,
            article_workers=article_workers,
            progress_cb=progress_cb,
            progress_label=name,
        )
        if not result.get('success'):
            _p(f'{name} · 수집 실패: {result.get("error")}', phase='feed_error', feed=name)
            return {
                'name': name,
                'source_id': source_id,
                'category': source_type,
                'success': False,
                'error': result.get('error') or '수집 실패',
            }

        n = result.get('today_articles', 0)
        _p(f'{name} · DB 저장 중… ({n}건)', phase='saving', feed=name, total=n)
        # GN 원천: 기사는 파생 '언론사 - 키워드 (GN)' source_id 로 적재
        # 일반 RSS: 이 source 로 적재
        db_result = db.save_articles_to_db(
            feed_name=name,
            rss_url=rss_url,
            articles=result['articles'],
            google_news_keyword=gn_keyword if is_gn_origin else None,
        )
        saved = db_result.get('saved', 0)
        skipped = db_result.get('skipped', 0)
        no_content = db_result.get('no_content', 0)
        _p(
            f'{name} · 저장 완료 · 저장 {saved} · 중복 {skipped} · 본문없음 {no_content}',
            phase='saved',
            feed=name,
            saved=saved,
            skipped=skipped,
            no_content=no_content,
        )
        return {
            'name': name,
            'source_id': source_id,
            'category': source_type,
            'success': True,
            'today_articles': n,
            'db': db_result,
        }
    except Exception as e:
        _p(f'{name} · 오류: {e}', phase='feed_error', feed=name)
        return {
            'name': name,
            'source_id': source_id,
            'category': source_type,
            'success': False,
            'error': str(e),
        }


def _run_save_all(progress_cb=None) -> dict:
    """
    전체 DB 저장: sources 테이블의 수집 가능 소스만 병렬 수집·저장.
    - 대상: http(s) RSS URL 이 있는 sources
    - 제외: Google News 파생 소스 (rss_url LIKE 'google_news://%')
      파생 소스는 UI에서 GN 키워드 수집 시 article 적재용이며,
      전체 저장에서 다시 수집하지 않음
    """
    def _p(msg, **kw):
        if progress_cb:
            try:
                progress_cb(msg, **kw)
            except Exception:
                pass

    try:
        jobs = db.list_collectible_sources()
    except Exception as e:
        _p(f'sources 조회 실패: {e}', phase='error')
        return {
            'total_saved': 0,
            'total_skipped': 0,
            'total_no_content': 0,
            'detail': [],
            'error': str(e),
            'parallel': {'feed_workers': 0, 'article_workers_per_feed': 0},
        }

    if not jobs:
        _p(
            '수집 대상 sources 가 없습니다. (Google News 파생 소스 제외 · http RSS 만)',
            phase='done',
        )
        return {
            'total_saved': 0,
            'total_skipped': 0,
            'total_no_content': 0,
            'detail': [],
            'parallel': {'feed_workers': 0, 'article_workers_per_feed': 0},
        }

    art_workers = (
        _ARTICLE_WORKERS_IN_BATCH if len(jobs) > 1 else _ARTICLE_WORKERS
    )
    feed_workers = min(_FEED_WORKERS, len(jobs))
    _p(
        f'전체 저장 시작 · sources {len(jobs)}개 (GN 파생 제외) · 병렬 {feed_workers}',
        phase='batch_start',
        total_feeds=len(jobs),
    )

    summary = [None] * len(jobs)
    finished = [0]
    fin_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=feed_workers) as pool:
        future_to_idx = {
            pool.submit(
                _process_one_source_for_save,
                source,
                art_workers,
                progress_cb,
            ): i
            for i, source in enumerate(jobs)
        }
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                summary[idx] = fut.result()
            except Exception as e:
                src = jobs[idx]
                summary[idx] = {
                    'name': src.get('name') or 'Unknown',
                    'source_id': src.get('source_id'),
                    'category': src.get('source_type') or '',
                    'success': False,
                    'error': str(e),
                }
            with fin_lock:
                finished[0] += 1
                _p(
                    f'진행 {finished[0]}/{len(jobs)} 출처 처리 완료',
                    phase='batch_progress',
                    current=finished[0],
                    total=len(jobs),
                )

    summary = [s for s in summary if s is not None]
    total_saved      = sum(s.get('db', {}).get('saved', 0)      for s in summary if s.get('success'))
    total_skipped    = sum(s.get('db', {}).get('skipped', 0)    for s in summary if s.get('success'))
    total_no_content = sum(s.get('db', {}).get('no_content', 0) for s in summary if s.get('success'))
    _p(
        f'전체 완료 · 저장 {total_saved} · 중복 {total_skipped} · 본문없음 {total_no_content}',
        phase='batch_done',
        total_saved=total_saved,
    )
    return {
        'total_saved': total_saved,
        'total_skipped': total_skipped,
        'total_no_content': total_no_content,
        'detail': summary,
        'parallel': {
            'feed_workers': feed_workers,
            'article_workers_per_feed': art_workers,
        },
    }


def _ndjson_response(worker_fn) -> StreamingResponse:
    """
    worker_fn(progress_cb) -> result dict
    progress_cb(message, **kw) 호출 시 NDJSON progress 라인 전송
    """
    q: queue.Queue = queue.Queue()

    def progress_cb(message, **kw):
        payload = {'type': 'progress', 'message': message}
        payload.update(kw)
        q.put(payload)

    def worker():
        try:
            result = worker_fn(progress_cb)
            q.put({'type': 'done', 'success': True, 'data': result})
        except Exception as e:
            q.put({'type': 'done', 'success': False, 'error': str(e)})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + '\n'

    return StreamingResponse(
        generate(),
        media_type='application/x-ndjson',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


def _parse_fetch_params(data: dict) -> dict:
    data = data or {}
    return {
        'url': data.get('url'),
        'limit': data.get('limit'),
        'include_yesterday': data.get('include_yesterday', False),
        'source_type': data.get('type') or data.get('source_type') or 'RSS',
        'keyword': data.get('keyword'),
        'name': data.get('name') or data.get('keyword') or '피드',
    }


def _err(error: str, status: int = 400) -> JSONResponse:
    return JSONResponse({'success': False, 'error': error}, status_code=status)


# ── Routes ────────────────────────────────────────────────────

@app.get('/', response_class=HTMLResponse)
def index():
    """메인 테스트 UI (정적 HTML — Jinja 변수 없음)"""
    return FileResponse(BASE_DIR / 'templates' / 'index.html')


@app.get('/api/categories')
def get_categories():
    """카테고리 목록 반환 (categories.json)"""
    return load_categories()


@app.post('/api/fetch')
def fetch_articles(data: Optional[dict[str, Any]] = Body(default=None)):
    """선택한 RSS에서 기사 가져오기 (동기 JSON)"""
    data = data or {}
    p = _parse_fetch_params(data)
    if not p['url']:
        return _err('URL이 필요합니다', 400)

    return fetch_rss_articles(
        p['url'],
        limit=p['limit'],
        include_yesterday=p['include_yesterday'],
        source_type=p['source_type'],
        keyword=p['keyword'],
        progress_label=p['name'],
    )


@app.post('/api/fetch-stream')
def fetch_articles_stream(data: Optional[dict[str, Any]] = Body(default=None)):
    """기사 수집 + NDJSON 진행 상황 스트림"""
    data = data or {}
    p = _parse_fetch_params(data)
    if not p['url']:
        return _err('URL이 필요합니다', 400)

    def work(progress_cb):
        return fetch_rss_articles(
            p['url'],
            limit=p['limit'],
            include_yesterday=p['include_yesterday'],
            source_type=p['source_type'],
            keyword=p['keyword'],
            progress_cb=progress_cb,
            progress_label=p['name'],
        )

    return _ndjson_response(work)


@app.get('/api/test')
def test_rss():
    """모든 RSS 테스트 (categories.json 기준, limit=1)"""
    categories = load_categories()
    results = {}

    for category, feeds in categories['categories'].items():
        results[category] = []
        for feed in feeds:
            st = feed.get('type') or 'RSS'
            result = fetch_rss_articles(
                feed['url'],
                limit=1,
                source_type=st,
                keyword=feed.get('keyword'),
                progress_label=feed.get('name'),
            )
            results[category].append({
                'name': feed['name'],
                'url': feed['url'],
                'status': '✅ 정상' if result.get('success') else '❌ 오류',
                'message': result.get('title', result.get('error', '')),
            })

    return results


@app.post('/api/add-source')
def add_source(data: Optional[dict[str, Any]] = Body(default=None)):
    """
    새 뉴스 출처 추가
    - type=RSS (기본): name + url
    - type=GOOGLE_NEWS: keyword 필수 → Google News RSS URL 자동 생성
    """
    data = data or {}
    category = (data.get('category') or '').strip()
    source_type = (data.get('type') or data.get('source_type') or 'RSS').strip().upper()
    if source_type in ('GOOGLENEWS', 'GN', 'GOOGLE'):
        source_type = 'GOOGLE_NEWS'

    if not category:
        return _err('카테고리를 선택하세요', 400)

    try:
        categories = load_categories()
        if category not in categories['categories']:
            categories['categories'][category] = []

        if source_type == 'GOOGLE_NEWS':
            keyword = (data.get('keyword') or data.get('name') or '').strip()
            if not keyword:
                return _err('검색 키워드를 입력하세요', 400)

            url = build_google_news_rss_url(keyword)
            name = f'Google News · {keyword}'

            for src in categories['categories'][category]:
                if (src.get('type') or '').upper() == 'GOOGLE_NEWS' and (
                    src.get('keyword') == keyword or src.get('url') == url
                ):
                    return _err('이미 등록된 키워드입니다', 409)

            entry = {
                'name': name,
                'url': url,
                'type': 'GOOGLE_NEWS',
                'keyword': keyword,
            }
            try:
                db_reg = db.register_google_news_origin(name, url, keyword)
                entry['source_id'] = db_reg.get('source_id')
                entry['db_created'] = db_reg.get('created')
            except Exception as e:
                return JSONResponse(
                    {
                        'success': False,
                        'error': f'categories 추가는 가능하나 sources DB 등록 실패: {e}',
                    },
                    status_code=500,
                )
        else:
            name = (data.get('name') or '').strip()
            url = (data.get('url') or '').strip()
            if not name or not url:
                return _err('출처 이름과 RSS URL을 입력하세요', 400)
            if not url.startswith('http'):
                return _err('URL은 http(s)://로 시작해야 합니다', 400)

            for src in categories['categories'][category]:
                if src.get('url') == url:
                    return _err('이미 등록된 RSS 주소입니다', 409)

            entry = {
                'name': name,
                'url': url,
                'type': 'RSS',
            }

        categories['categories'][category].append(entry)
        save_categories(categories)

        msg = f'"{entry["name"]}" 추가됨'
        if source_type == 'GOOGLE_NEWS' and entry.get('db_created'):
            msg += f' · sources 등록 (id={entry.get("source_id")})'
        elif source_type == 'GOOGLE_NEWS' and entry.get('source_id'):
            msg += f' · sources 기존 연결 (id={entry.get("source_id")})'

        return {
            'success': True,
            'message': msg,
            'categories': categories,
            'source': entry,
        }
    except Exception as e:
        return _err(str(e), 500)


@app.post('/api/delete-source')
def delete_source(data: Optional[dict[str, Any]] = Body(default=None)):
    """출처 삭제 (categories.json 만 — DB sources/articles 는 유지)"""
    data = data or {}
    category = data.get('category')
    source_name = data.get('source_name')

    if not category or not source_name:
        return _err('카테고리와 출처명이 필요합니다', 400)

    try:
        categories = load_categories()

        if category not in categories['categories']:
            return _err('존재하지 않는 카테고리입니다', 404)

        original_length = len(categories['categories'][category])
        categories['categories'][category] = [
            source for source in categories['categories'][category]
            if source['name'] != source_name
        ]

        if len(categories['categories'][category]) == original_length:
            return _err('출처를 찾을 수 없습니다', 404)

        save_categories(categories)

        return {
            'success': True,
            'message': f'"{source_name}" 삭제됨',
            'categories': categories,
        }
    except Exception as e:
        return _err(str(e), 500)


@app.post('/api/fetch-and-save')
def fetch_and_save(data: Optional[dict[str, Any]] = Body(default=None)):
    """RSS 기사 가져오기 + DB 저장 (본문 실패 건은 저장 안 함)"""
    data = data or {}
    p = _parse_fetch_params(data)
    if not p['url']:
        return _err('URL이 필요합니다', 400)

    feed_name = data.get('name', p['name'] or 'Unknown')
    result = fetch_rss_articles(
        p['url'],
        include_yesterday=p['include_yesterday'],
        source_type=p['source_type'],
        keyword=p['keyword'],
        progress_label=feed_name,
    )
    if not result.get('success'):
        return JSONResponse(result, status_code=500)

    is_gn = result.get('is_google_news') or (p['source_type'] or '').upper() in (
        'GOOGLE_NEWS', 'GOOGLENEWS', 'GN'
    )
    db_result = db.save_articles_to_db(
        feed_name=feed_name,
        rss_url=p['url'],
        articles=result['articles'],
        google_news_keyword=(p['keyword'] or result.get('keyword')) if is_gn else None,
    )

    return {
        'success': True,
        'feed_title': result.get('title'),
        'today_articles': result['today_articles'],
        'failed': result.get('failed', 0),
        'db': db_result,
    }


@app.post('/api/fetch-and-save-stream')
def fetch_and_save_stream(data: Optional[dict[str, Any]] = Body(default=None)):
    """수집+DB 저장 NDJSON 진행 스트림"""
    data = data or {}
    p = _parse_fetch_params(data)
    if not p['url']:
        return _err('URL이 필요합니다', 400)
    feed_name = data.get('name', p['name'] or 'Unknown')

    def work(progress_cb):
        progress_cb(f'{feed_name} · 수집 시작', phase='start', feed=feed_name)
        result = fetch_rss_articles(
            p['url'],
            include_yesterday=p['include_yesterday'],
            source_type=p['source_type'],
            keyword=p['keyword'],
            progress_cb=progress_cb,
            progress_label=feed_name,
        )
        if not result.get('success'):
            raise RuntimeError(result.get('error') or '수집 실패')

        is_gn = result.get('is_google_news') or (p['source_type'] or '').upper() in (
            'GOOGLE_NEWS', 'GOOGLENEWS', 'GN'
        )
        n = result.get('today_articles', 0)
        progress_cb(f'{feed_name} · DB 저장 중… ({n}건)', phase='saving', feed=feed_name)
        db_result = db.save_articles_to_db(
            feed_name=feed_name,
            rss_url=p['url'],
            articles=result['articles'],
            google_news_keyword=(p['keyword'] or result.get('keyword')) if is_gn else None,
        )
        progress_cb(
            f'{feed_name} · 저장 완료 · 저장 {db_result.get("saved", 0)}건',
            phase='saved',
            feed=feed_name,
        )
        return {
            'success': True,
            'feed_title': result.get('title'),
            'today_articles': result['today_articles'],
            'failed': result.get('failed', 0),
            'db': db_result,
        }

    return _ndjson_response(work)


@app.post('/api/save-all')
def save_all():
    """전체 수집·저장 (동기 JSON — 호환용)"""
    result = _run_save_all(progress_cb=None)
    return {'success': True, **result}


@app.post('/api/save-all-stream')
def save_all_stream():
    """전체 수집·저장 + NDJSON 진행 스트림"""
    return _ndjson_response(lambda progress_cb: _run_save_all(progress_cb=progress_cb))


@app.get('/api/db-stats')
def db_stats():
    """DB 저장 현황 조회"""
    return db.get_db_stats()


if __name__ == '__main__':
    import uvicorn

    print('📡 서버 시작: http://localhost:5000')
    print('🔗 테스트 UI: http://localhost:5000/')
    print('📘 API 문서:  http://localhost:5000/docs')
    uvicorn.run('app:app', host='127.0.0.1', port=5000, reload=True)
