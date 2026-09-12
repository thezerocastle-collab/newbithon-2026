from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from geopy.distance import geodesic

app = FastAPI(title="밤이 작아지는 서울 - 공간 데이터 API")

# 프론트/메인팀에서 전달받을 입력을 위한 데이터 모델
class Station(BaseModel):
    name: str
    lat: float
    lon: float

class QueryRequest(BaseModel):
    stations: List[Station]
    category: Optional[str] = None  # 특정 카테고리만 필터링할 경우 (선택)

@app.post("/places/nearby")
def get_nearby_places(req: QueryRequest):
    conn = sqlite3.connect("places.db")
    cursor = conn.cursor()
    
    # 모든 장소 조회
    if req.category:
        cursor.execute("SELECT id, name, category, address, road_address, lat, lon FROM places WHERE category = ?", (req.category,))
    else:
        cursor.execute("SELECT id, name, category, address, road_address, lat, lon FROM places")
        
    all_places = cursor.fetchall()
    conn.close()
    
    matched_places = {}  # 장소 ID 기준 중복 제거용 Dict

    # 도달 가능한 각 역에 대해 500m 반경 내 장소 추출
    for station in req.stations:
        station_loc = (station.lat, station.lon)
        
        for p in all_places:
            place_id, name, category, address, road_address, lat, lon = p
            place_loc = (lat, lon)
            
            # 실제 지표면 거리(미터) 계산
            dist = geodesic(station_loc, place_loc).meters
            
            if dist <= 500:  # 반경 500m 이내
                # 중복 장소 처리: 더 가까운 역의 거리로 업데이트
                if place_id not in matched_places or matched_places[place_id]['distance'] > dist:
                    matched_places[place_id] = {
                        "id": place_id,
                        "name": name,
                        "category": category,
                        "address": address,
                        "road_address": road_address,
                        "lat": lat,
                        "lon": lon,
                        "nearest_station": station.name,
                        "distance": round(dist, 1)
                    }

    return {
        "count": len(matched_places),
        "places": list(matched_places.values())
    }