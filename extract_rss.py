import pandas as pd
import os
import re
from pathlib import Path

def extract_rss_urls(excel_file):
    """Excel 파일에서 RSS URL 추출"""
    try:
        # 모든 시트 읽기
        xls = pd.ExcelFile(excel_file, engine='openpyxl')
        urls = set()
        
        print(f"📄 {os.path.basename(excel_file)} 처리 중...")
        
        for sheet in xls.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet)
            
            # 모든 셀에서 URL 찾기
            for col in df.columns:
                for value in df[col]:
                    if pd.notna(value):
                        value_str = str(value).strip()
                        # http 또는 https로 시작하는 URL 찾기
                        if value_str.startswith('http://') or value_str.startswith('https://'):
                            urls.add(value_str)
        
        return urls
    except Exception as e:
        print(f"❌ 오류: {e}")
        return set()

def validate_rss_url(url):
    """RSS URL 유효성 검사"""
    try:
        import feedparser
        feed = feedparser.parse(url)
        
        # RSS 피드 여부 확인
        if hasattr(feed, 'entries') and len(feed.entries) > 0:
            return True, feed.feed.get('title', 'Unknown')
        elif hasattr(feed, 'feed') and feed.feed:
            return True, feed.feed.get('title', 'Unknown')
        else:
            return False, None
    except:
        return False, None

# Excel 파일 찾기
excel_files = [
    "AX뉴스레터_경제_경영_사이트.xlsx",
    "뉴스레터_문화_건강_사이트조사.xlsx",
    "economy_newsletter_scraping_plan-v7.xlsx",
    "국제_뉴스레터_기획서.xlsx"
]

all_urls = set()

for file in excel_files:
    # 여러 위치에서 파일 찾기
    search_paths = [
        Path(file),
        Path.home() / "Downloads" / file,
        Path.home() / "Desktop" / file,
        Path("/tmp") / file,
    ]
    
    for path in search_paths:
        if path.exists():
            urls = extract_rss_urls(str(path))
            all_urls.update(urls)
            break

if all_urls:
    print(f"\n✅ 총 {len(all_urls)}개 URL 발견\n")
    print("검증 중...\n")
    
    valid_rss = []
    
    for url in sorted(all_urls):
        is_valid, title = validate_rss_url(url)
        status = "✅" if is_valid else "❌"
        print(f"{status} {url}")
        if title:
            print(f"   └─ {title}\n")
        if is_valid:
            valid_rss.append({"url": url, "title": title})
    
    # 결과 저장
    if valid_rss:
        print(f"\n📊 검증된 RSS: {len(valid_rss)}개\n")
        for item in valid_rss:
            print(f"- Name: {item['title']}")
            print(f"  URL: {item['url']}\n")
else:
    print("Excel 파일을 찾을 수 없습니다.")
    print("현재 디렉토리:", os.getcwd())
    print("파일 목록:", os.listdir())
