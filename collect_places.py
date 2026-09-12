import requests
import pandas as pd
import time
import os

# 1. 카카오 REST API 키
KAKAO_REST_API_KEY = "23cd2df6c34ebeb9a0141d0770358641"

url = "https://dapi.kakao.com/v2/local/search/keyword.json"
headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}

# 2. 서울시 25개 자치구 목록
seoul_districts = [
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
    "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
    "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"
]

# 스터디카페 검색 키워드 패턴
search_terms = ["24시 스터디카페", "스터디카페"]

all_places = []

print("서울 전역 24시 스터디카페 데이터 수집 시작...")

for district in seoul_districts:
    for term in search_terms:
        query_str = f"서울 {district} {term}"
        
        for page in range(1, 4):
            params = {
                "query": query_str,
                "page": page,
                "size": 15
            }
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                documents = data.get('documents', [])
                
                for place in documents:
                    all_places.append({
                        "id": place["id"],
                        "name": place["place_name"],
                        "category": "study_cafe",
                        "address": place["address_name"],
                        "road_address": place["road_address_name"],
                        "lat": float(place["y"]),
                        "lon": float(place["x"])
                    })
                
                if data.get('meta', {}).get('is_end', True):
                    break
            else:
                print(f"오류 발생 ({query_str}): {response.status_code}")
                break
                
            time.sleep(0.05)

# 3. 데이터프레임 변환 및 중복 제거
df = pd.DataFrame(all_places)
if not df.empty:
    df = df.drop_duplicates(subset=["id"]).reset_index(drop=True)

# 4. CSV 파일로 저장
os.makedirs("data", exist_ok=True)
csv_path = "data/seoul_study_cafes.csv"
df.to_csv(csv_path, index=False, encoding="utf-8-sig")

print(f"\n수집 완료! 중복 제거 후 총 {len(df)}개의 스터디카페가 '{csv_path}'에 저장되었습니다.")