import requests
import urllib3
import re
urllib3.disable_warnings()

url = 'https://www.chosun.com/politics/goverment/2026/07/28/NJNSPCSTINHOFHGC4XP2OTIZPM/'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'
}
resp = requests.get(url, headers=headers, verify=False)
resp.encoding = resp.apparent_encoding

# URL에서 기사 ID 추출
match = re.search(r'/(\w+)/$', url)
if match:
    article_id = match.group(1)
    print(f"Article ID: {article_id}\n")
    
    # Fusion API 시도
    api_urls = [
        f'https://www.chosun.com/papi/v2/stories/{article_id}?website=arc',
        f'https://api.chosun.com/graphql',
        f'https://www.chosun.com/api/v2/arc/story/{article_id}',
        f'https://www.chosun.com/arc/api/v1/stories/{article_id}',
    ]
    
    for api_url in api_urls:
        try:
            r = requests.get(api_url, headers=headers, verify=False, timeout=5)
            if r.status_code == 200:
                print(f"✓ {api_url}")
                print(f"  Response: {r.text[:300]}")
                print()
        except:
            print(f"✗ {api_url}")

# GraphQL 요청 확인
print("\nNetwork 요청 추적 (HTML 분석):")
if 'window.store' in resp.text:
    print("Found: window.store")
    start = resp.text.find('window.store')
    print(resp.text[start:start+500])

