# -*- coding: utf-8 -*-
"""
News Collect 기술 문서 PDF 생성기
"""
from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

# ── 경로 / 폰트 ──────────────────────────────────────────────
OUT_DIR = Path(__file__).resolve().parent
OUT_PDF = OUT_DIR / "News_Collect_Technical_Documentation.pdf"

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\NanumGothic.ttf",
    r"C:\Windows\Fonts\NotoSansKR-Regular.otf",
]
FONT_BOLD_CANDIDATES = [
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\malgun.ttf",
]


def _register_fonts():
    regular = next((p for p in FONT_CANDIDATES if os.path.isfile(p)), None)
    bold = next((p for p in FONT_BOLD_CANDIDATES if os.path.isfile(p)), regular)
    if not regular:
        raise RuntimeError("한글 폰트(malgun.ttf 등)를 찾을 수 없습니다.")
    pdfmetrics.registerFont(TTFont("KR", regular))
    pdfmetrics.registerFont(TTFont("KR-Bold", bold))
    return "KR", "KR-Bold"


# ── 색상 ─────────────────────────────────────────────────────
C_PRIMARY = colors.HexColor("#312E81")      # indigo-900
C_ACCENT = colors.HexColor("#4F46E5")       # indigo-600
C_ACCENT_SOFT = colors.HexColor("#EEF2FF")  # indigo-50
C_TEXT = colors.HexColor("#111827")
C_MUTED = colors.HexColor("#6B7280")
C_LINE = colors.HexColor("#E5E7EB")
C_HEAD_BG = colors.HexColor("#1E1B4B")
C_ROW_ALT = colors.HexColor("#F9FAFB")
C_OK = colors.HexColor("#059669")
C_CODE_BG = colors.HexColor("#F3F4F6")
C_WHITE = colors.white


def build_styles(font, font_bold):
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="CoverTitle",
        fontName=font_bold,
        fontSize=26,
        leading=34,
        textColor=C_WHITE,
        alignment=TA_CENTER,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="CoverSub",
        fontName=font,
        fontSize=12,
        leading=18,
        textColor=colors.HexColor("#C7D2FE"),
        alignment=TA_CENTER,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="CoverMeta",
        fontName=font,
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#A5B4FC"),
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="H1",
        fontName=font_bold,
        fontSize=16,
        leading=22,
        textColor=C_PRIMARY,
        spaceBefore=16,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="H2",
        fontName=font_bold,
        fontSize=12.5,
        leading=17,
        textColor=C_ACCENT,
        spaceBefore=12,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="H3",
        fontName=font_bold,
        fontSize=10.5,
        leading=14,
        textColor=C_TEXT,
        spaceBefore=8,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Body",
        fontName=font,
        fontSize=9.5,
        leading=14.5,
        textColor=C_TEXT,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="BodyLeft",
        fontName=font,
        fontSize=9.5,
        leading=14,
        textColor=C_TEXT,
        alignment=TA_LEFT,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BodyBullet",
        fontName=font,
        fontSize=9.5,
        leading=13.5,
        textColor=C_TEXT,
        leftIndent=12,
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="Note",
        fontName=font,
        fontSize=8.5,
        leading=12,
        textColor=C_MUTED,
        leftIndent=4,
        spaceBefore=2,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="TableCell",
        fontName=font,
        fontSize=8,
        leading=11,
        textColor=C_TEXT,
    ))
    styles.add(ParagraphStyle(
        name="TableHead",
        fontName=font_bold,
        fontSize=8,
        leading=11,
        textColor=C_WHITE,
    ))
    styles.add(ParagraphStyle(
        name="CodeBlock",
        fontName=font,
        fontSize=7.5,
        leading=10.5,
        textColor=C_TEXT,
        backColor=C_CODE_BG,
        leftIndent=4,
        rightIndent=4,
        spaceBefore=4,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="CodeInlineKR",
        fontName=font,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1F2937"),
    ))
    styles.add(ParagraphStyle(
        name="Footer",
        fontName=font,
        fontSize=8,
        textColor=C_MUTED,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="TOC",
        fontName=font,
        fontSize=10,
        leading=16,
        textColor=C_TEXT,
        leftIndent=8,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="Caption",
        fontName=font,
        fontSize=8,
        leading=11,
        textColor=C_MUTED,
        alignment=TA_CENTER,
        spaceBefore=2,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="APIMethod",
        fontName=font_bold,
        fontSize=9,
        leading=12,
        textColor=C_ACCENT,
    ))
    return styles


def p(styles, text, style="Body"):
    return Paragraph(text.replace("\n", "<br/>"), styles[style])


def hr():
    return HRFlowable(width="100%", thickness=0.6, color=C_LINE, spaceBefore=4, spaceAfter=8)


def make_table(headers, rows, col_widths, styles):
    head = [Paragraph(h, styles["TableHead"]) for h in headers]
    body = []
    for row in rows:
        body.append([Paragraph(str(c), styles["TableCell"]) for c in row])
    data = [head] + body
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "KR-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, C_LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 1), (-1, -1), C_WHITE),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), C_ROW_ALT))
    t.setStyle(TableStyle(style_cmds))
    return t


def code_block(text, styles, width=170 * mm):
    # Preformatted with Korean font
    style = ParagraphStyle(
        "PreKR",
        fontName="KR",
        fontSize=7.2,
        leading=9.8,
        textColor=C_TEXT,
        backColor=C_CODE_BG,
        leftIndent=6,
        rightIndent=6,
        spaceBefore=4,
        spaceAfter=8,
        borderPadding=6,
    )
    # escape for Paragraph
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
        .replace(" ", "&nbsp;")
    )
    return Paragraph(f"<font face='KR' size='7.2'>{safe}</font>", style)


def flow_diagram_table(styles):
    """ASCII-like flow as a styled multi-row table"""
    steps = [
        ["1", "출처 등록", "categories.json 및/또는 sources 테이블\n(일반 RSS / Google News 키워드)"],
        ["2", "RSS 수집", "feedparser + curl_cffi (Cloudflare 대응)"],
        ["3", "날짜 필터", "로컬 타임존 기준 오늘 / 오늘+어제"],
        ["4", "URL 해석", "Google News → 원문 URL (googlenewsdecoder)"],
        ["5", "본문 추출", "사이트 전용 파서 → Readability → BS4"],
        ["6", "품질 검증", "푸터/AI요약/잘림 거부, 본문 실패 시 미저장"],
        ["7", "DB 적재", "sources upsert → articles insert (URL UNIQUE)"],
    ]
    data = [[Paragraph(x, styles["TableHead"]) for x in ["단계", "프로세스", "설명"]]]
    for s in steps:
        data.append([Paragraph(c, styles["TableCell"]) for c in s])
    t = Table(data, colWidths=[18 * mm, 32 * mm, 120 * mm])
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
        ("BACKGROUND", (0, 1), (0, -1), C_ACCENT_SOFT),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, C_LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    t.setStyle(TableStyle(cmds))
    return t


def architecture_table(styles):
    rows = [
        ["프레젠테이션", "HTML / CSS / Vanilla JS", "테스트·디버그 UI, 진행 로그"],
        ["API 계층", "Flask + flask-cors", "REST JSON / NDJSON 스트림"],
        ["수집 엔진", "feedparser, curl_cffi, requests", "RSS 파싱, 브라우저 impersonate"],
        ["본문 추출", "readability-lxml, BeautifulSoup", "사이트별 전용 파서 포함"],
        ["URL 해석", "googlenewsdecoder", "Google News 리다이렉트 해제"],
        ["병렬 처리", "concurrent.futures", "피드·기사 단위 ThreadPool"],
        ["영속 계층", "PostgreSQL + psycopg3", "sources / articles"],
        ["설정", "categories.json, config.json", "출처 목록 · DB 접속 정보"],
    ]
    return make_table(
        ["계층", "기술", "역할"],
        rows,
        [28 * mm, 52 * mm, 90 * mm],
        styles,
    )


def source_type_table(styles):
    rows = [
        ["일반 언론 RSS", "매일경제 - 경제", "https://www.mk.co.kr/rss/...", "전체 저장 O · 자체 RSS 수집"],
        ["GN 원천", "Google News · 증권", "https://news.google.com/rss/search?q=...", "전체 저장 O · 키워드 수집 트리거"],
        ["GN 파생", "매일경제 - 증권 (GN)", "google_news://증권/매일경제", "전체 저장 X · 기사 적재 전용"],
    ]
    return make_table(
        ["종류", "name 예시", "rss_url 예시", "전체 저장"],
        rows,
        [28 * mm, 38 * mm, 62 * mm, 42 * mm],
        styles,
    )


def api_overview_table(styles):
    rows = [
        ["GET", "/", "테스트 UI"],
        ["GET", "/api/categories", "카테고리·출처 목록"],
        ["POST", "/api/add-source", "출처 추가 (RSS / GOOGLE_NEWS)"],
        ["POST", "/api/delete-source", "출처 삭제 (categories.json)"],
        ["POST", "/api/fetch", "단건 수집 (미리보기)"],
        ["POST", "/api/fetch-stream", "단건 수집 + 진행 스트림"],
        ["POST", "/api/fetch-and-save", "단건 수집 + DB 저장"],
        ["POST", "/api/fetch-and-save-stream", "단건 수집·저장 + 스트림"],
        ["POST", "/api/save-all", "전체 저장 (sources 기준)"],
        ["POST", "/api/save-all-stream", "전체 저장 + 스트림 ★"],
        ["GET", "/api/test", "전 피드 연결 스모크 테스트"],
        ["GET", "/api/db-stats", "DB 적재 통계"],
    ]
    return make_table(
        ["Method", "Path", "설명"],
        rows,
        [22 * mm, 58 * mm, 90 * mm],
        styles,
    )


def footer_canvas(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
    canvas.setFont("KR", 8)
    canvas.setFillColor(C_MUTED)
    canvas.drawString(18 * mm, 7 * mm, "News Collect · Technical Documentation")
    canvas.drawRightString(A4[0] - 18 * mm, 7 * mm, f"{doc.page}")
    canvas.restoreState()


def cover_page(styles, story):
    # Cover block via table with background
    cover_data = [[
        Paragraph("News Collect", styles["CoverTitle"]),
    ], [
        Paragraph("뉴스 수집 · 본문 추출 · DB 저장 파이프라인", styles["CoverSub"]),
    ], [
        Paragraph("Technical Architecture &amp; API Reference", styles["CoverSub"]),
    ], [
        Paragraph("Version 1.0 &nbsp;|&nbsp; 2026-08-05 &nbsp;|&nbsp; Confidential — Internal Use", styles["CoverMeta"]),
    ]]
    cover = Table(cover_data, colWidths=[170 * mm])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
        ("TOPPADDING", (0, 0), (-1, 0), 48),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 40),
        ("TOPPADDING", (0, 1), (-1, -2), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
    ]))
    story.append(Spacer(1, 30 * mm))
    story.append(cover)
    story.append(Spacer(1, 16 * mm))

    # Document info box
    info_rows = [
        ["문서 유형", "시스템 기술 명세서 / API 레퍼런스"],
        ["대상 시스템", "news_collect (Flask RSS Ingestion Service)"],
        ["주요 독자", "백엔드·프론트엔드 연동 개발자, 아키텍트"],
        ["Base URL", "http://&lt;host&gt;:5000"],
        ["데이터 저장소", "PostgreSQL (news_collect)"],
    ]
    info = make_table(["항목", "내용"], info_rows, [40 * mm, 130 * mm], styles)
    story.append(info)
    story.append(Spacer(1, 12 * mm))
    story.append(p(styles,
        "본 문서는 뉴스 RSS 수집부터 본문 추출, PostgreSQL 적재까지의 전체 데이터 파이프라인, "
        "기술 스택, REST API 명세, 프론트엔드 연동 시나리오를 정의한다. "
        "테스트 UI는 디버깅용이며, 프로덕션 배치는 <b>sources 테이블 기준 전체 저장 API</b>를 사용한다.",
        "Body"))
    story.append(PageBreak())


def toc(styles, story):
    story.append(p(styles, "목차", "H1"))
    story.append(hr())
    items = [
        "1. 개요 및 시스템 목표",
        "2. 기술 스택",
        "3. 아키텍처 및 데이터 모델",
        "4. 수집 → 저장 엔드투엔드 플로우",
        "5. Google News 원천·파생 소스 모델",
        "6. API 전체 목록 및 상세 명세",
        "7. 프론트엔드 연동 시나리오 (API 사용 예시)",
        "8. 오류 처리 · 품질 게이트 · 성능",
        "9. 운영 및 연동 가이드라인",
    ]
    for it in items:
        story.append(p(styles, it, "TOC"))
    story.append(PageBreak())


def build_document():
    font, font_bold = _register_fonts()
    styles = build_styles(font, font_bold)
    story = []

    # ── Cover & TOC ──
    cover_page(styles, story)
    toc(styles, story)

    # ── 1. Overview ──
    story.append(p(styles, "1. 개요 및 시스템 목표", "H1"))
    story.append(hr())
    story.append(p(styles,
        "<b>News Collect</b>는 다수 언론·포털 RSS 피드를 수집하고, 기사 원문 HTML에서 본문을 추출한 뒤 "
        "PostgreSQL에 구조화하여 저장하는 인제스천(Ingestion) 서비스이다. "
        "웹 UI는 수집 품질을 검증하기 위한 <b>테스트·디버그 콘솔</b>이며, "
        "실제 운영 배치의 기준 데이터는 <b>sources / articles</b> 테이블이다."))

    story.append(p(styles, "1.1 핵심 목표", "H2"))
    for t in [
        "언론사별 RSS 및 Google News 키워드 RSS를 단일 파이프라인으로 수집",
        "봇 차단·인코딩·사이트 구조 차이에 강건한 HTTP 및 본문 추출",
        "본문 수집 실패 기사 제외, URL 기준 중복 방지",
        "Google News 파생 소스와 일반 RSS 소스의 명확한 분리 및 배치 수집 정책",
        "메인 서비스(프론트/배치)가 호출 가능한 명시적 REST API 제공",
    ]:
        story.append(p(styles, f"• {t}", "BodyBullet"))

    story.append(p(styles, "1.2 논리적 구성요소", "H2"))
    story.append(make_table(
        ["구성", "책임", "비고"],
        [
            ["Test UI", "출처 관리, 단건 미리보기, 진행 로그", "categories.json 중심"],
            ["Collection API", "RSS 파싱 · 본문 추출", "동기 / NDJSON 스트림"],
            ["Persistence API", "sources·articles 적재", "전체 저장은 DB sources 기준"],
            ["PostgreSQL", "영속 저장소", "UNIQUE source_url 로 멱등성"],
        ],
        [32 * mm, 70 * mm, 68 * mm],
        styles,
    ))
    story.append(PageBreak())

    # ── 2. Tech stack ──
    story.append(p(styles, "2. 기술 스택", "H1"))
    story.append(hr())
    story.append(p(styles, "2.1 계층별 기술", "H2"))
    story.append(architecture_table(styles))
    story.append(p(styles, "그림 2-1. 계층별 기술 스택 요약", "Caption"))

    story.append(p(styles, "2.2 주요 라이브러리 역할", "H2"))
    story.append(make_table(
        ["패키지", "역할"],
        [
            ["Flask / flask-cors", "HTTP API 서버, CORS, 스트리밍 응답"],
            ["feedparser", "RSS/Atom XML 파싱"],
            ["curl_cffi", "Chrome TLS/JA3 impersonate — Cloudflare 등 우회"],
            ["requests", "HTTP 폴백"],
            ["readability-lxml", "본문 후보 영역 추출 (Mozilla Readability)"],
            ["beautifulsoup4 / lxml", "HTML 파싱, 사이트별 DOM 추출"],
            ["googlenewsdecoder", "Google News 기사 토큰 → 원문 URL"],
            ["python-dateutil", "발행일 파싱 및 로컬 타임존 날짜 변환"],
            ["psycopg (v3)", "PostgreSQL 접속 및 트랜잭션"],
            ["chardet", "응답 인코딩 추정"],
        ],
        [42 * mm, 128 * mm],
        styles,
    ))

    story.append(p(styles, "2.3 런타임·인프라 가정", "H2"))
    story.append(p(styles,
        "• Python 3.12+ (개발 환경 기준 3.14 동작 확인)<br/>"
        "• PostgreSQL 14+ , DB명 기본값 <b>news_collect</b><br/>"
        "• 접속 정보는 <b>config.json</b> 의 database 블록<br/>"
        "• 개발 서버: <b>Flask debug, port 5000</b> (운영 시 WSGI 권장)"))
    story.append(PageBreak())

    # ── 3. Architecture & Data Model ──
    story.append(p(styles, "3. 아키텍처 및 데이터 모델", "H1"))
    story.append(hr())
    story.append(p(styles, "3.1 논리 아키텍처", "H2"))
    story.append(p(styles,
        "클라이언트(테스트 UI 또는 메인 프론트) → Flask API → "
        "수집 엔진(RSS/HTTP/추출) → PostgreSQL. "
        "설정 파일(categories.json)은 UI 테스트용 출처 목록이고, "
        "배치 수집의 진실 공급원(Source of Truth)은 <b>sources</b> 테이블이다."))

    arch_flow = [
        ["Client", "→", "Flask API", "→", "Ingestion Engine", "→", "PostgreSQL"],
        ["(Web/App)", "", "(REST/NDJSON)", "", "(RSS+Scrape)", "", "(sources/articles)"],
    ]
    at = Table(arch_flow, colWidths=[24 * mm, 8 * mm, 28 * mm, 8 * mm, 32 * mm, 8 * mm, 32 * mm])
    at.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), C_ACCENT_SOFT),
        ("BACKGROUND", (2, 0), (2, 0), C_ACCENT),
        ("BACKGROUND", (4, 0), (4, 0), C_PRIMARY),
        ("BACKGROUND", (6, 0), (6, 0), colors.HexColor("#064E3B")),
        ("TEXTCOLOR", (2, 0), (2, 0), C_WHITE),
        ("TEXTCOLOR", (4, 0), (4, 0), C_WHITE),
        ("TEXTCOLOR", (6, 0), (6, 0), C_WHITE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "KR-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "KR"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (0, 0), 0.5, C_ACCENT),
        ("BOX", (2, 0), (2, 0), 0.5, C_ACCENT),
        ("BOX", (4, 0), (4, 0), 0.5, C_PRIMARY),
        ("BOX", (6, 0), (6, 0), 0.5, colors.HexColor("#064E3B")),
    ]))
    story.append(at)
    story.append(p(styles, "그림 3-1. 논리 아키텍처 개요", "Caption"))

    story.append(p(styles, "3.2 sources 테이블", "H2"))
    story.append(code_block(
        "CREATE TABLE sources (\n"
        "  source_id          BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,\n"
        "  name               VARCHAR(200) NOT NULL,\n"
        "  rss_url            VARCHAR(1000) UNIQUE,\n"
        "  source_type        VARCHAR(20) NOT NULL\n"
        "    CHECK (source_type IN ('공식발표','통신사','전문미디어','포털API','커뮤니티')),\n"
        "  credibility_weight NUMERIC(3,2) NOT NULL CHECK (0..1),\n"
        "  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()\n"
        ");",
        styles,
    ))

    story.append(p(styles, "3.3 articles 테이블", "H2"))
    story.append(code_block(
        "CREATE TABLE articles (\n"
        "  article_id      BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,\n"
        "  source_id       BIGINT NOT NULL REFERENCES sources(source_id),\n"
        "  source_url      VARCHAR(1000) NOT NULL UNIQUE,  -- 원문 URL, 중복 스킵 키\n"
        "  title           VARCHAR(500) NOT NULL,\n"
        "  cleaned_content TEXT,       -- 추출 본문\n"
        "  raw_content     TEXT,       -- 원문 HTML\n"
        "  published_at    TIMESTAMPTZ,\n"
        "  collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        "  status          VARCHAR(20) DEFAULT 'collected'\n"
        "    CHECK (status IN ('collected','processed','summarized','archived'))\n"
        ");",
        styles,
    ))

    story.append(p(styles, "3.4 소스 유형 매트릭스 (운영 핵심)", "H2"))
    story.append(source_type_table(styles))
    story.append(p(styles, "표 3-1. 소스 유형별 식별자 및 전체 저장 포함 여부", "Caption"))
    story.append(p(styles,
        "<b>규칙 요약:</b> 전체 저장 대상 = <b>http(s) RSS</b> 이면서 "
        "<b>rss_url NOT LIKE 'google_news://%'</b> 이고 "
        "<b>name NOT LIKE '% (GN)'</b>. "
        "파생 소스는 기사 적재 대상일 뿐, 배치 수집 루프의 입력으로 사용하지 않는다.",
        "Body"))
    story.append(PageBreak())

    # ── 4. E2E Flow ──
    story.append(p(styles, "4. 수집 → 저장 엔드투엔드 플로우", "H1"))
    story.append(hr())
    story.append(p(styles, "4.1 단계별 파이프라인", "H2"))
    story.append(flow_diagram_table(styles))
    story.append(p(styles, "표 4-1. 인제스천 파이프라인 7단계", "Caption"))

    story.append(p(styles, "4.2 단건 수집 (UI 테스트 / 미리보기)", "H2"))
    story.append(p(styles,
        "사용자가 카테고리·소스를 선택하면 프론트는 <b>POST /api/fetch-stream</b> 을 호출한다. "
        "서버는 RSS를 읽고 날짜 필터 후 기사별로 병렬 본문 추출을 수행하며, "
        "진행 상황을 NDJSON 으로 푸시한다. DB에는 쓰지 않는다."))

    story.append(p(styles, "4.3 단건 수집 + 저장", "H2"))
    story.append(p(styles,
        "<b>POST /api/fetch-and-save-stream</b>: 수집 후 저장. "
        "type=RSS 이면 sources.name/url 로 upsert 후 동일 source_id 에 articles insert. "
        "type=GOOGLE_NEWS 이면 기사마다 publisher 를 읽어 "
        "<b>{언론사} - {키워드} (GN)</b> 파생 source 를 만들고 그 ID 로 저장한다."))

    story.append(p(styles, "4.4 전체 DB 저장 (프로덕션 배치 경로)", "H2"))
    story.append(p(styles,
        "<b>POST /api/save-all-stream</b> 이 운영의 기본 진입점이다. "
        "categories.json 이 아니라 <b>list_collectible_sources()</b> 결과(DB)를 순회한다. "
        "피드 병렬(기본 4) × 기사 병렬(배치 시 기본 4)로 처리한다. "
        "Google News 원천 URL(news.google.com)은 GOOGLE_NEWS 경로로 수집하고, "
        "기사는 파생 (GN) 소스에 적재한다. 파생 소스 자체는 순회 목록에 없다."))

    story.append(p(styles, "4.5 본문 추출 우선순위", "H2"))
    story.append(make_table(
        ["우선순위", "방법", "대상 예"],
        [
            ["0", "사이트 전용 파서", "조선 Fusion, 한경, 동아, 매경, GeekNews"],
            ["1", "Readability", "일반 뉴스 페이지"],
            ["2", "JSON-LD articleBody", "스키마 제공 사이트 (잘린 본문 거부)"],
            ["3", "BeautifulSoup 셀렉터", "공통 CSS 후보"],
        ],
        [22 * mm, 48 * mm, 100 * mm],
        styles,
    ))
    story.append(p(styles,
        "거부 조건: 언론사 푸터 오탐, AI 요약 블록(매경 핵심요약 쏙 등), "
        "말줄임(...)으로 끝나는 잘린 본문, 본문 공백/실패 문구. "
        "실패 기사는 DB에 넣지 않고 no_content 로 집계한다."))
    story.append(PageBreak())

    # ── 5. Google News ──
    story.append(p(styles, "5. Google News 원천·파생 소스 모델", "H1"))
    story.append(hr())
    story.append(p(styles,
        "Google News 검색 RSS는 단일 언론사가 아니라 다수 언론 기사를 묶는다. "
        "따라서 원천 키워드 피드와 기사 단위 언론사 소스를 분리한다."))

    story.append(p(styles, "5.1 등록 시", "H2"))
    story.append(p(styles,
        "UI에서 Google News + 키워드 추가 시:<br/>"
        "1) categories.json 에 type=GOOGLE_NEWS 항목 추가<br/>"
        "2) sources 에 원천 행 INSERT — name=<b>Google News · {키워드}</b>, "
        "rss_url=실제 news.google.com 검색 URL, source_type=포털API"))

    story.append(p(styles, "5.2 수집·저장 시", "H2"))
    story.append(p(styles,
        "1) Google RSS entry 의 source.title → publisher<br/>"
        "2) googlenewsdecoder 로 원문 URL 해석<br/>"
        "3) 원문 본문 추출<br/>"
        "4) sources upsert: name=<b>{publisher} - {keyword} (GN)</b>, "
        "rss_url=<b>google_news://{keyword}/{publisher}</b><br/>"
        "5) articles.insert(source_id=파생 ID)<br/><br/>"
        "일반 RSS <b>매일경제 - 경제</b> 와 파생 <b>매일경제 - 경제 (GN)</b> 은 "
        "이름·URL 모두 달라 충돌하지 않는다. 파생 소스는 rss_url 로만 매칭한다."))

    story.append(p(styles, "5.3 전체 저장 포함/제외", "H2"))
    story.append(make_table(
        ["소스", "전체 저장 루프", "기사 적재"],
        [
            ["Google News · 증권 (원천)", "포함 — 키워드 수집 실행", "직접 적재하지 않음 (트리거)"],
            ["매일경제 - 증권 (GN) (파생)", "제외", "GN 수집 시 적재"],
            ["매일경제 - 경제 (일반 RSS)", "포함 — 자체 RSS 수집", "해당 source_id 로 적재"],
        ],
        [48 * mm, 55 * mm, 67 * mm],
        styles,
    ))
    story.append(PageBreak())

    # ── 6. API Spec ──
    story.append(p(styles, "6. API 전체 목록 및 상세 명세", "H1"))
    story.append(hr())
    story.append(p(styles, "6.1 엔드포인트 총괄", "H2"))
    story.append(api_overview_table(styles))
    story.append(p(styles, "표 6-1. API 엔드포인트 목록 (Base URL: http://host:5000)", "Caption"))

    story.append(p(styles, "6.2 공통 규칙", "H2"))
    story.append(p(styles,
        "• Content-Type: application/json (스트림 제외)<br/>"
        "• 스트림 API: application/x-ndjson , 라인 단위 JSON<br/>"
        "• 성공/실패: 대부분 { success: bool, ... } 또는 HTTP 4xx/5xx<br/>"
        "• 날짜 필터: 서버 로컬 타임존 달력 기준 (UTC date() 직접 사용 안 함)<br/>"
        "• 본문 실패 문구: \"본문을 가져올 수 없습니다.\" — DB 미저장"))

    # API details
    apis = [
        ("GET /", "UI", "테스트 콘솔 HTML 반환. 인증 없음."),
        ("GET /api/categories", "설정",
         "categories.json 전체 로드. 응답: { categories: { [cat]: Source[] } }. "
         "Source: name, url, type(RSS|GOOGLE_NEWS), keyword?(GN)."),
        ("POST /api/add-source", "설정",
         "Body(RSS): { category, type:'RSS', name, url }. "
         "Body(GN): { category, type:'GOOGLE_NEWS', keyword }. "
         "GN은 categories.json + sources 원천 동시 등록. "
         "409 중복, 400 검증 오류."),
        ("POST /api/delete-source", "설정",
         "Body: { category, source_name }. categories.json 에서만 삭제. "
         "DB sources 행은 현재 자동 삭제하지 않음."),
        ("POST /api/fetch", "수집",
         "Body: { url, type?, keyword?, name?, include_yesterday?, limit? }. "
         "수집만 수행. articles[] 반환. is_google_news, failed 카운트 포함."),
        ("POST /api/fetch-stream", "수집",
         "fetch 와 동일 파라미터. NDJSON progress + done.data."),
        ("POST /api/fetch-and-save", "수집+저장",
         "수집 후 DB 저장. Body에 name 권장. "
         "응답: today_articles, failed, db:{saved,skipped,no_content,errors}."),
        ("POST /api/fetch-and-save-stream", "수집+저장",
         "위와 동일 + NDJSON 진행 스트림."),
        ("POST /api/save-all", "배치",
         "DB sources 수집 가능 목록 전체 처리. Body 없음. 동기 JSON. "
         "detail[] 에 출처별 결과."),
        ("POST /api/save-all-stream", "배치 ★",
         "save-all 의 스트리밍 버전. 프로덕션 배치·UI 전체 저장 권장."),
        ("GET /api/test", "디버그",
         "categories.json 전 피드 limit=1 스모크. 시간 소요 큼."),
        ("GET /api/db-stats", "모니터링",
         "sources_count, articles_count, top_sources[] 반환."),
    ]
    story.append(p(styles, "6.3 엔드포인트별 상세", "H2"))
    for path, role, desc in apis:
        story.append(p(styles, f"<b>{path}</b>  <font color='#6B7280'>[{role}]</font>", "H3"))
        story.append(p(styles, desc, "BodyLeft"))

    story.append(p(styles, "6.4 수집 공통 요청 필드", "H2"))
    story.append(make_table(
        ["필드", "타입", "필수", "설명"],
        [
            ["url", "string", "Y", "RSS URL"],
            ["type", "string", "N", "RSS | GOOGLE_NEWS (기본 RSS)"],
            ["keyword", "string", "GN 시", "검색 키워드, 파생 source 이름에 사용"],
            ["name", "string", "N", "로그·표시용 출처명"],
            ["include_yesterday", "bool", "N", "true=오늘+어제"],
            ["limit", "int", "N", "피드 entry 상한(디버그)"],
        ],
        [38 * mm, 22 * mm, 18 * mm, 92 * mm],
        styles,
    ))

    story.append(p(styles, "6.5 수집 응답 article 객체", "H2"))
    story.append(make_table(
        ["필드", "설명"],
        [
            ["title", "정제된 제목 (GN은 언론사 접미 제거)"],
            ["content", "추출 본문 또는 실패 문구"],
            ["raw_content", "원문 HTML (저장 시 articles.raw_content)"],
            ["link", "원문 URL (GN은 해석 후 URL)"],
            ["published", "RSS 발행 시각 문자열"],
            ["method", "추출기 이름 (MkBody, ChosunFusion, Readability, 실패 등)"],
            ["publisher", "언론사 (주로 GN)"],
            ["keyword", "GN 키워드"],
        ],
        [36 * mm, 134 * mm],
        styles,
    ))

    story.append(p(styles, "6.6 NDJSON 스트림 포맷", "H2"))
    story.append(code_block(
        '{"type":"progress","message":"매일경제 - 경제 · 수집 중… 3/12건",'
        '"phase":"collecting","current":3,"total":12}\n'
        '{"type":"progress","message":"매일경제 - 경제 · 저장 완료 · 저장 10","phase":"saved"}\n'
        '{"type":"done","success":true,"data":{ ... 최종 결과 객체 ... }}\n'
        '{"type":"done","success":false,"error":"에러 메시지"}',
        styles,
    ))
    story.append(p(styles,
        "phase 예: batch_start, feed_start, fetch_rss, collect_start, collecting, "
        "collect_done, saving, saved, batch_progress, batch_done, error, feed_error"))
    story.append(PageBreak())

    # ── 7. Frontend integration ──
    story.append(p(styles, "7. 프론트엔드 연동 시나리오 (API 사용 예시)", "H1"))
    story.append(hr())
    story.append(p(styles,
        "아래 예시는 메인 웹앱(React/Vue/Next 등) 또는 배치 워커가 동일 API를 호출하는 패턴이다. "
        "Base URL 은 환경변수로 주입한다."))

    story.append(p(styles, "7.1 시나리오 A — 출처 목록 로드", "H2"))
    story.append(code_block(
        "GET /api/categories\n\n"
        "// 응답을 카테고리 탭 + 소스 칩으로 렌더\n"
        "// type==='GOOGLE_NEWS' 이면 배지 GN, label=keyword\n"
        "const { categories } = await res.json();\n"
        "Object.entries(categories).forEach(([cat, sources]) => { ... });",
        styles,
    ))

    story.append(p(styles, "7.2 시나리오 B — 일반 RSS 출처 등록", "H2"))
    story.append(code_block(
        "POST /api/add-source\n"
        "Content-Type: application/json\n\n"
        "{\n"
        '  "category": "경제/경영",\n'
        '  "type": "RSS",\n'
        '  "name": "연합뉴스 - 경제",\n'
        '  "url": "https://www.yna.co.kr/rss/economy.xml"\n'
        "}\n\n"
        "// 성공 시 categories 전체를 다시 받아 상태 갱신\n"
        "// 실제 sources 테이블 반영은 이후 fetch-and-save 또는 배치 시 upsert",
        styles,
    ))

    story.append(p(styles, "7.3 시나리오 C — Google News 키워드 등록", "H2"))
    story.append(code_block(
        "POST /api/add-source\n\n"
        "{\n"
        '  "category": "IT",\n'
        '  "type": "GOOGLE_NEWS",\n'
        '  "keyword": "인공지능"\n'
        "}\n\n"
        "// 서버 동작:\n"
        "// 1) categories.json 에 GOOGLE_NEWS 항목 추가\n"
        "// 2) sources 에 원천 INSERT\n"
        '//    name="Google News · 인공지능"\n'
        "//    rss_url=https://news.google.com/rss/search?q=...\n"
        '//    source_type="포털API"\n'
        "// 응답 source.source_id, source.db_created 확인",
        styles,
    ))

    story.append(p(styles, "7.4 시나리오 D — 단건 미리보기 (수집만)", "H2"))
    story.append(code_block(
        "POST /api/fetch-stream\n\n"
        "{\n"
        '  "url": "https://www.mk.co.kr/rss/30100041/",\n'
        '  "type": "RSS",\n'
        '  "name": "매일경제 - 경제",\n'
        '  "include_yesterday": false\n'
        "}\n\n"
        "// 클라이언트: ReadableStream 으로 줄 단위 JSON 파싱\n"
        "// type==='progress' → 토스트/로그 UI 갱신\n"
        "// type==='done' && success → data.articles 로 리스트 렌더\n"
        "// article.publisher 있으면 언론사 뱃지 표시 (주로 GN)",
        styles,
    ))

    story.append(p(styles, "7.5 시나리오 E — 단건 수집 후 DB 저장", "H2"))
    story.append(code_block(
        "POST /api/fetch-and-save-stream\n\n"
        "{\n"
        '  "name": "Google News · 증권",\n'
        '  "url": "https://news.google.com/rss/search?q=%EC%A6%9D%EA%B6%8C&hl=ko&gl=KR&ceid=KR:ko",\n'
        '  "type": "GOOGLE_NEWS",\n'
        '  "keyword": "증권",\n'
        '  "include_yesterday": true\n'
        "}\n\n"
        "// 진행 로그 예:\n"
        '// "Google News · 증권 · RSS 불러오는 중…"\n'
        '// "Google News · 증권 · 수집 중… 5/20건"\n'
        '// "Google News · 증권 · DB 저장 중… (20건)"\n'
        '// "Google News · 증권 · 저장 완료 · 저장 15건"\n'
        "// done.data.db = { saved, skipped, no_content, errors }\n"
        "// 기사별 sources 예: \"한겨레 - 증권 (GN)\", rss_url=google_news://증권/한겨레",
        styles,
    ))

    story.append(p(styles, "7.6 시나리오 F — 프로덕션 일배치 (전체 저장) ★", "H2"))
    story.append(p(styles,
        "스케줄러(cron, Airflow, Cloud Scheduler 등) 또는 관리자 UI 버튼이 호출한다. "
        "UI의 categories.json 과 무관하게, 그 시점 DB sources 의 수집 가능 행만 처리한다."))
    story.append(code_block(
        "POST /api/save-all-stream\n"
        "Content-Type: application/json\n\n"
        "{}\n\n"
        "// 서버 내부:\n"
        "// sources WHERE http(s) AND NOT google_news:// AND name NOT LIKE '% (GN)'\n"
        "// 각 source:\n"
        "//   - news.google.com 이면 type=GOOGLE_NEWS, keyword 복원 후 수집\n"
        "//     → 기사는 파생 (GN) source 로 insert\n"
        "//   - 그 외 RSS 는 type=RSS\n"
        "//     → 해당 source_id 로 insert\n"
        "// 병렬: feed_workers=4, article_workers_per_feed=4 (설정값)\n\n"
        "// done.data:\n"
        "// {\n"
        '//   "total_saved": 152,\n'
        '//   "total_skipped": 40,\n'
        '//   "total_no_content": 8,\n'
        '//   "detail": [ { name, source_id, success, db:{...} }, ... ],\n'
        '//   "parallel": { "feed_workers": 4, "article_workers_per_feed": 4 }\n'
        "// }",
        styles,
    ))

    story.append(p(styles, "7.7 시나리오 G — 프론트에서 sources 목록 정책", "H2"))
    story.append(p(styles,
        "메인 앱이 수집 가능 언론 목록을 보여줄 때 <b>SELECT * FROM sources</b> 를 그대로 쓰면 "
        "파생 (GN) 행까지 노출된다. 수집 대상으로 쓸 목록은 아래와 동일 조건으로 필터한다."))
    story.append(code_block(
        "-- 수집 대상 sources (서버 list_collectible_sources 와 동일 취지)\n"
        "SELECT source_id, name, rss_url, source_type\n"
        "FROM sources\n"
        "WHERE rss_url IS NOT NULL\n"
        "  AND rss_url <> ''\n"
        "  AND rss_url NOT LIKE 'google_news://%'\n"
        "  AND name NOT LIKE '% (GN)'\n"
        "  AND (rss_url LIKE 'http://%' OR rss_url LIKE 'https://%')\n"
        "ORDER BY source_id;\n\n"
        "-- 기사 피드는 보통 articles 기준 조회 (파생 source 기사 포함 가능)\n"
        "SELECT a.*, s.name AS source_name\n"
        "FROM articles a\n"
        "JOIN sources s ON s.source_id = a.source_id\n"
        "WHERE a.published_at >= now() - interval '1 day'\n"
        "ORDER BY a.published_at DESC;",
        styles,
    ))

    story.append(p(styles, "7.8 NDJSON 클라이언트 의사코드", "H2"))
    story.append(code_block(
        "async function readNdjson(url, body, onProgress) {\n"
        "  const res = await fetch(url, {\n"
        "    method: 'POST',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify(body || {}),\n"
        "  });\n"
        "  const reader = res.body.getReader();\n"
        "  const dec = new TextDecoder();\n"
        "  let buf = '', final = null;\n"
        "  while (true) {\n"
        "    const { value, done } = await reader.read();\n"
        "    if (done) break;\n"
        "    buf += dec.decode(value, { stream: true });\n"
        "    const lines = buf.split('\\n'); buf = lines.pop();\n"
        "    for (const line of lines) {\n"
        "      if (!line.trim()) continue;\n"
        "      const obj = JSON.parse(line);\n"
        "      if (obj.type === 'progress') onProgress(obj);\n"
        "      if (obj.type === 'done') final = obj;\n"
        "    }\n"
        "  }\n"
        "  return final; // { success, data } | { success:false, error }\n"
        "}",
        styles,
    ))
    story.append(PageBreak())

    # ── 8. Errors / Quality / Perf ──
    story.append(p(styles, "8. 오류 처리 · 품질 게이트 · 성능", "H1"))
    story.append(hr())
    story.append(p(styles, "8.1 저장 게이트", "H2"))
    story.append(make_table(
        ["조건", "결과"],
        [
            ["본문 null / 공백 / 실패 문구", "no_content, INSERT 안 함"],
            ["source_url 이미 존재", "skipped (중복)"],
            ["본문 정상 + 신규 URL", "saved"],
            ["기타 DB 오류", "errors"],
        ],
        [70 * mm, 100 * mm],
        styles,
    ))

    story.append(p(styles, "8.2 추출 품질 필터", "H2"))
    story.append(p(styles,
        "• 사이트 푸터(등록번호, 발행·편집인 등) 오탐 거부<br/>"
        "• 매경 등 AI 요약 모달(Key Points, OpenAI 문구) 제거·거부<br/>"
        "• 말줄임(...) 으로 끝나는 잘린 JSON-LD/본문 거부 (GeekNews 등)<br/>"
        "• 조선: Fusion.globalContent / 동아: section.news_view / 한경: .article-body 등"))

    story.append(p(styles, "8.3 성능 파라미터", "H2"))
    story.append(make_table(
        ["파라미터", "기본값", "의미"],
        [
            ["_ARTICLE_WORKERS", "8", "단건 수집 시 기사 병렬 수"],
            ["_FEED_WORKERS", "4", "전체 저장 시 소스 병렬 수"],
            ["_ARTICLE_WORKERS_IN_BATCH", "4", "전체 저장 시 소스당 기사 병렬"],
            ["GN URL 캐시", "프로세스 메모리", "동일 구글 링크 재해석 방지"],
        ],
        [48 * mm, 28 * mm, 94 * mm],
        styles,
    ))
    story.append(p(styles,
        "대략 동시 HTTP ≈ feed_workers × article_workers_in_batch. "
        "과도한 상향은 대상 사이트 차단 위험이 있다."))

    story.append(p(styles, "8.4 HTTP 상태 가이드", "H2"))
    story.append(make_table(
        ["코드", "상황"],
        [
            ["200", "정상 JSON / 스트림 완료"],
            ["400", "필수 파라미터 누락·검증 실패"],
            ["404", "delete-source 시 카테고리/출처 없음"],
            ["409", "중복 출처/키워드"],
            ["500", "서버·DB·수집 예외"],
        ],
        [22 * mm, 148 * mm],
        styles,
    ))
    story.append(PageBreak())

    # ── 9. Ops ──
    story.append(p(styles, "9. 운영 및 연동 가이드라인", "H1"))
    story.append(hr())
    story.append(p(styles, "9.1 환경 설정", "H2"))
    story.append(code_block(
        "// config.json\n"
        "{\n"
        '  "database": {\n'
        '    "host": "localhost",\n'
        '    "port": 5432,\n'
        '    "dbname": "news_collect",\n'
        '    "user": "postgres",\n'
        '    "password": "****"\n'
        "  }\n"
        "}",
        styles,
    ))

    story.append(p(styles, "9.2 메인 서비스 연동 체크리스트", "H2"))
    for t in [
        "프로덕션 배치는 POST /api/save-all-stream 사용 (진행 관측 + 타임아웃 여유)",
        "수집 가능 소스 목록 UI는 list_collectible_sources 조건과 동일한 필터 적용",
        "기사 피드는 articles 조인 조회; (GN) 소스 기사 포함 여부는 제품 정책에 따름",
        "categories.json 은 테스트 UI 전용으로 취급, 배치 SoT 는 sources 테이블",
        "삭제 API의 DB 연동(원천/파생 cascade)이 필요하면 후속 개발 항목으로 명시",
        "운영 배포 시 Flask dev 서버 대신 gunicorn/waitress + reverse proxy",
        "Google/언론사 rate limit 모니터링, 워커 수 조정",
    ]:
        story.append(p(styles, f"• {t}", "BodyBullet"))

    story.append(p(styles, "9.3 권장 호출 맵 (메인 앱)", "H2"))
    story.append(make_table(
        ["사용자/시스템 행동", "API"],
        [
            ["관리: RSS/키워드 등록", "POST /api/add-source"],
            ["관리: 테스트 UI 목록", "GET /api/categories"],
            ["운영: 매일 배치 수집", "POST /api/save-all-stream"],
            ["운영: 특정 소스만 재수집", "POST /api/fetch-and-save-stream"],
            ["모니터링: 적재량", "GET /api/db-stats"],
            ["디버그: 본문 품질 확인", "POST /api/fetch-stream"],
        ],
        [55 * mm, 115 * mm],
        styles,
    ))

    story.append(Spacer(1, 10 * mm))
    story.append(hr())
    story.append(p(styles,
        "문서 끝. 본 명세는 news_collect 코드베이스(app.py, db.py, schema.sql, 프론트 static) "
        "구현 시점 기준이다. API 변경 시 본 문서와 버전을 함께 갱신한다.",
        "Note"))

    # Build PDF
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT_PDF),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="News Collect Technical Documentation",
        author="News Collect Engineering",
        subject="Architecture, Data Flow, and API Reference",
    )
    doc.build(story, onFirstPage=footer_canvas, onLaterPages=footer_canvas)
    return OUT_PDF


if __name__ == "__main__":
    path = build_document()
    print("WROTE", path)
    print("SIZE", path.stat().st_size)
