import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv


# =========================
# 0. 기본 설정
# =========================

CACHE_FILE = "route_cache.json"

load_dotenv()

APP_KEY = os.getenv("SK_APP_KEY")

if not APP_KEY:
    print("SK_APP_KEY가 없습니다. .env 파일을 확인하세요.")
    exit()

URL = "https://apis.openapi.sk.com/transit/routes"


# =========================
# 1. 장소 좌표
# =========================

places = {
    # 서북권
    "홍대": (126.9237, 37.5563),
    "신촌": (126.9369, 37.5552),
    "불광": (126.9303, 37.6105),

    # 도심권
    "서울역": (126.9707, 37.5547),
    "종로": (126.9830, 37.5704),
    "동대문": (127.0090, 37.5714),

    # 동북권
    "안암": (127.0294, 37.5863),
    "왕십리": (127.0371, 37.5615),
    "수유": (127.0255, 37.6370),
    "노원": (127.0618, 37.6551),

    # 동부권
    "건대": (127.0692, 37.5404),
    "천호": (127.1238, 37.5386),
    "잠실": (127.1001, 37.5133),

    # 강남권
    "강남": (127.0276, 37.4979),
    "교대": (127.0142, 37.4934),
    "사당": (126.9816, 37.4765),

    # 서남권
    "신림": (126.9297, 37.4842),
    "구로": (126.8826, 37.5030),
    "영등포": (126.9073, 37.5155),
    "여의도": (126.9240, 37.5216),

    # 중부 / 용산권
    "용산": (126.9648, 37.5298),
    "마포": (126.9458, 37.5396)
}

# =========================
# 2. 확인할 목적지
# =========================

test_destinations = list(places.keys())

# 지도에서 선택할 시간대
TIME_SLOTS = [
    "22:30",
    "23:00",
    "23:30",
    "00:00",
    "00:30"
]


# =========================
# 3. 캐시 불러오기
# =========================

def load_cache():

    if os.path.exists(CACHE_FILE):

        try:
            with open(
                CACHE_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                return json.load(f)

        except (json.JSONDecodeError, OSError):
            return {}

    return {}


# =========================
# 4. 캐시 저장
# =========================

def save_cache(cache):

    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2
        )


# =========================
# 5. 경로 확인 함수
# =========================

def check_route(
    start_lon,
    start_lat,
    end_lon,
    end_lat,
    search_time
):

    # -------------------------
    # 캐시 확인
    # -------------------------

    cache = load_cache()

    cache_key = (
        f"{start_lon},{start_lat}_"
        f"{end_lon},{end_lat}_"
        f"{search_time.strftime('%Y%m%d%H%M')}"
    )

    # 이미 계산했던 경로라면
    # API를 호출하지 않음
    if cache_key in cache:

        print("💾 캐시 사용")

        return cache[cache_key]


    # -------------------------
    # API 요청 준비
    # -------------------------

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "appKey": APP_KEY
    }

    data = {
        "startX": str(start_lon),
        "startY": str(start_lat),

        "endX": str(end_lon),
        "endY": str(end_lat),

        # 후보 경로 3개 확인
        "count": 3,

        "lang": 0,
        "format": "json",

        "searchDttm":
            search_time.strftime("%Y%m%d%H%M")
    }


    # -------------------------
    # API 호출
    # -------------------------

    try:

        response = requests.post(
            URL,
            headers=headers,
            json=data,
            timeout=10
        )

    except requests.RequestException as e:

        print("네트워크 오류:", e)

        return None


    # -------------------------
    # API 오류 처리
    # -------------------------

    if response.status_code == 429:

        print("⚠️ API 호출 한도 초과")

        return None


    if response.status_code != 200:

        print(
            "API 오류:",
            response.status_code,
            response.text[:200]
        )

        return None


    # -------------------------
    # JSON 응답 읽기
    # -------------------------

    api_data = response.json()

    itineraries = (
        api_data
        .get("metaData", {})
        .get("plan", {})
        .get("itineraries", [])
    )


    # -------------------------
    # 경로 자체가 없는 경우
    # -------------------------

    if not itineraries:

        result = {
            "reachable": False,
            "total_time": None,
            "transfers": None
        }

        cache[cache_key] = result

        save_cache(cache)

        return result


    # =========================
    # 6. 후보 경로 확인
    # =========================

    for route in itineraries:

        reachable = True


        # 이 경로에 포함된
        # 지하철 / 버스 구간 확인
        for leg in route.get("legs", []):

            mode = leg.get("mode")

            service = leg.get("service")


            if mode in ["SUBWAY", "BUS"]:

                # 하나라도 운행 종료면
                # 이 경로는 사용 불가능
                if service == 0:

                    reachable = False

                    break


        # -------------------------
        # 끝까지 갈 수 있는 경로 발견
        # -------------------------

        if reachable:

            result = {
                "reachable": True,

                "total_time": round(
                    route.get(
                        "totalTime",
                        0
                    ) / 60
                ),

                "transfers": route.get(
                    "transferCount",
                    0
                )
            }


            # 결과 저장
            cache[cache_key] = result

            save_cache(cache)


            return result


    # =========================
    # 7. 모든 후보 경로 실패
    # =========================

    result = {
        "reachable": False,
        "total_time": None,
        "transfers": None
    }


    # 실패 결과도 저장
    cache[cache_key] = result

    save_cache(cache)


    return result


# =========================
# 8. 사용자 입력
# =========================

start_name = input(
    "출발 장소 입력: "
).strip()


if start_name not in places:

    print("등록되지 않은 장소입니다.")

    print(
        "가능한 장소:",
        ", ".join(places.keys())
    )

    exit()


date_text = input(
    "날짜 입력 (예: 20260912): "
).strip()


print("\n시간대를 선택하세요.")

for i, time_slot in enumerate(TIME_SLOTS, start=1):
    print(f"{i}. {time_slot}")

try:
    time_choice = int(
        input("번호 입력 (1~5): ")
    )

    if time_choice < 1 or time_choice > len(TIME_SLOTS):
        raise ValueError

    time_text = TIME_SLOTS[time_choice - 1]

except ValueError:
    print("올바른 번호를 입력하세요.")
    exit()


try:

    search_time = datetime.strptime(
        date_text + time_text,
        "%Y%m%d%H:%M"
    )
        # 00시대는 입력한 날짜의 다음 날로 처리
    if search_time.hour < 3:
        search_time += timedelta(days=1)

except ValueError:

    print(
        "날짜 또는 시간 형식이 잘못됐습니다."
    )

    print(
        "예: 20260912 / 23:40"
    )

    exit()


# 출발지 좌표
start_lon, start_lat = places[start_name]


# =========================
# 9. 목적지 확인
# =========================

results = []


print("\n======================")

print(
    "출발지:",
    start_name
)

print(
    "출발 시간:",
    search_time.strftime(
        "%Y-%m-%d %H:%M"
    )
)

print("======================\n")


for name in test_destinations:


    # 출발지와 목적지가 같으면
    # 검사할 필요 없음
    if name == start_name:

        continue


    end_lon, end_lat = places[name]


    print(
        name,
        "확인 중..."
    )


    route_result = check_route(
        start_lon,
        start_lat,
        end_lon,
        end_lat,
        search_time
    )


    # API 자체가 실패했다면
    # 추가 호출하지 않고 즉시 중단
    if route_result is None:

        print(
            "API 호출 중단"
        )

        break


    # -------------------------
    # 프론트에 넘길 결과
    # -------------------------

    result = {
        "name": name,

        "lat": end_lat,

        "lon": end_lon,

        "reachable":
            route_result["reachable"],

        "total_time":
            route_result["total_time"],

        "transfers":
            route_result["transfers"]
    }


    results.append(result)


    # -------------------------
    # 터미널 출력
    # -------------------------

    if result["reachable"]:

        print(
            "✅",
            result["total_time"],
            "분 / 환승",
            result["transfers"],
            "회"
        )

    else:

        print(
            "❌ 도달 불가"
        )


# =========================
# 10. 프론트용 JSON 생성
# =========================

output = {

    "start": {

        "name": start_name,

        "lat": start_lat,

        "lon": start_lon
    },

    "datetime":
        search_time.strftime(
            "%Y-%m-%d %H:%M"
        ),

    "results": results
}


with open(
    "reachability.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        output,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    "\nreachability.json 저장 완료"
)