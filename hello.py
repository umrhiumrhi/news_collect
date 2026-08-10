import feedparser
import requests
import json
from datetime import datetime
from pathlib import Path
import urllib3
import ssl

# SSL 인증서 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# SSL 검증 비활성화 (테스트용)
import certifi
import os
os.environ['SSL_CERT_FILE'] = certifi.where()

class NewsletterAgent:
    """RSS 피드에서 뉴스를 수집하는 에이전트"""
    
    def __init__(self, rss_url):
        self.rss_url = rss_url
        self.articles = []
    
    def fetch_news(self):
        """RSS 피드에서 뉴스 기사 가져오기"""
        try:
            print(f"📰 RSS 피드 수집 중: {self.rss_url}")
            
            # User-Agent 지정 (일부 서버 호환성)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # requests로 먼저 콘텐츠 가져오기
            response = requests.get(self.rss_url, headers=headers, verify=False, timeout=10)
            response.raise_for_status()
            
            # feedparser로 파싱
            feed = feedparser.parse(response.content)
            
            if feed.bozo:
                print(f"⚠️ 경고: {feed.bozo_exception}")
            
            print(f"✅ '{feed.feed.get('title', 'Unknown')}' 에서 {len(feed.entries)}개 기사 발견\n")
            
            for entry in feed.entries:
                article = {
                    'title': entry.get('title', 'N/A'),
                    'summary': entry.get('summary', 'N/A'),
                    'link': entry.get('link', 'N/A'),
                    'published': entry.get('published', 'N/A'),
                }
                self.articles.append(article)
            
            return self.articles
        
        except Exception as e:
            print(f"❌ 오류: {str(e)}")
            return None
    
    def display_articles(self, limit=5):
        """수집한 기사 표시"""
        if not self.articles:
            print("수집된 기사가 없습니다.")
            return
        
        print(f"🔝 최신 {min(limit, len(self.articles))}개 기사:\n")
        
        for i, article in enumerate(self.articles[:limit], 1):
            print(f"{'='*80}")
            print(f"[{i}] {article['title']}")
            print(f"📅 {article['published']}")
            print(f"🔗 {article['link']}")
            print(f"\n📝 본문:\n{article['summary'][:300]}...")
            print()

# 사용 예시
if __name__ == "__main__":
    config_path = Path("config.json")
    
    if not config_path.exists():
        print("❌ config.json 파일을 찾을 수 없습니다.")
        exit()
    
    # config.json에서 RSS 피드 읽기
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    rss_feeds = config.get("rss_feeds", [])
    
    if not rss_feeds:
        print("❌ config.json에 RSS 피드가 없습니다.")
        exit()
    
    # 각 RSS 피드에서 뉴스 수집
    for feed_info in rss_feeds:
        print(f"\n{'='*80}")
        print(f"🔄 {feed_info['name']} 처리 중...")
        print('='*80)
        
        agent = NewsletterAgent(feed_info['url'])
        agent.fetch_news()
        agent.display_articles(limit=3)