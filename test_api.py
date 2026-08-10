import requests
import json

# 조선일보 - 경제 테스트
response = requests.post('http://localhost:5000/api/fetch', 
    json={'url': 'https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml'},
    timeout=30
)

data = response.json()
print("API 응답 상태:", response.status_code)
print("성공:", data.get('success'))
print("총 기사 수:", data.get('count'))
print("본문 미수집 수:", data.get('failed'))
print()

if data.get('articles'):
    print("첫 기사:")
    print(json.dumps(data['articles'][0], ensure_ascii=False, indent=2)[:500])
