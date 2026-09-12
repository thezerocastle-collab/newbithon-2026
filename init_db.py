import pandas as pd
import sqlite3
import os

# 1. DB 연결
conn = sqlite3.connect("places.db")
cursor = conn.cursor()

# 기존 테이블 삭제 후 새로 생성 (깔끔한 재초기화)
cursor.execute("DROP TABLE IF EXISTS places")
cursor.execute("""
CREATE TABLE places (
    id TEXT PRIMARY KEY,
    name TEXT,
    category TEXT,
    address TEXT,
    road_address TEXT,
    lat REAL,
    lon REAL
)
""")

# 2. data 폴더 안의 모든 CSV 파일 읽기
data_dir = "data"
csv_files = [f for f in os.listdir(data_dir) if f.endswith(".csv")]

total_count = 0

for file in csv_files:
    file_path = os.path.join(data_dir, file)
    df = pd.read_csv(file_path)
    
    for _, row in df.iterrows():
        try:
            cursor.execute("""
            INSERT OR IGNORE INTO places (id, name, category, address, road_address, lat, lon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(row.get('id', '')),
                str(row.get('name', '')),
                str(row.get('category', '')),
                str(row.get('address', '')),
                str(row.get('road_address', '')),
                float(row['lat']),
                float(row['lon'])
            ))
            if cursor.rowcount > 0:
                total_count += 1
        except Exception as e:
            continue

conn.commit()
conn.close()

print(f"DB 저장 완료! 총 {total_count}개의 장소 데이터가 'places.db'에 등록되었습니다.")