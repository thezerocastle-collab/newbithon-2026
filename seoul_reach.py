import os
import json
import requests

from datetime import datetime, timedelta
from dotenv import load_dotenv


# ==================================================
# 0. 기본 설정
# ==================================================

CACHE_FILE = "route_cache.json"
PLACES_FILE = "places.json"
OUTPUT_FILE = "reachability.json"

CACHE_TTL_HOURS = 24

URL = "https://apis.openapi.sk.com/transit/routes"


# ==================================================
# 1. API 키 불러오기
# ==================================================

load_dotenv()

APP_KEY = os.getenv("SK_APP_KEY")


if not APP_KEY:

    print("❌ SK_APP_KEY가 없습니다.")
    print(".env 파일을 확인하세요.")

    exit()


# ==================================================
# 2. 장소 데이터 불러오기
# ==================================================

try:

    with open(
        PLACES_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        places_data = json.load(f)


except FileNotFoundError:

    print(
        f"❌ {PLACES_FILE} 파일이 없습니다."
    )

    exit()


except json.JSONDecodeError:

    print(
        f"❌ {PLACES_FILE}의 JSON 형식이 잘못되었습니다."
    )

    exit()


# places.json
#
# {
#   "강남역": {
#       "lon": 127.0276,
#       "lat": 37.4979
#   }
# }

places = {

    name: (
        info["lon"],
        info["lat"]
    )

    for name, info in places_data.items()
}


print(
    f"📍 대표 지역 {len(places)}개 로드 완료"
)


# ==================================================
# 3. 사용 가능한 시간대
# ==================================================

TIME_SLOTS = [

    "22:30",
    "23:00",
    "23:30",
    "00:00",
    "00:30"

]


# ==================================================
# 4. 캐시 불러오기
# ==================================================

def load_cache():

    if not os.path.exists(
        CACHE_FILE
    ):

        return {}


    try:

        with open(
            CACHE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)


    except (
        json.JSONDecodeError,
        OSError
    ):

        return {}


# ==================================================
# 5. 캐시 파일 저장
# ==================================================

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


# ==================================================
# 6. 결과를 캐시에 저장
# ==================================================

def save_result_to_cache(
    cache,
    cache_key,
    result
):

    cache[cache_key] = {

        "cached_at":
            datetime.now().isoformat(
                timespec="seconds"
            ),

        "result":
            result
    }


    save_cache(
        cache
    )


# ==================================================
# 7. 캐시 결과 확인
# ==================================================

def get_cached_result(
    cache,
    cache_key
):

    if cache_key not in cache:

        return None


    cached_data = (
        cache[cache_key]
    )


    try:

        cached_at_text = (
            cached_data[
                "cached_at"
            ]
        )

        cached_result = (
            cached_data[
                "result"
            ]
        )


        cached_at = (
            datetime.fromisoformat(
                cached_at_text
            )
        )


        cache_age = (
            datetime.now()
            -
            cached_at
        )


        # -------------------------
        # 24시간 이내
        # -------------------------

        if cache_age < timedelta(
            hours=CACHE_TTL_HOURS
        ):

            print(
                "   💾 24시간 이내 캐시 사용"
            )

            return cached_result


        # -------------------------
        # 24시간 초과
        # -------------------------

        print(
            "   ♻️ 오래된 캐시 삭제"
        )


        del cache[
            cache_key
        ]


        save_cache(
            cache
        )


        return None


    except (
        KeyError,
        TypeError,
        ValueError
    ):

        # 예전 버전 캐시:
        #
        # {
        #   "reachable": true,
        #   ...
        # }
        #
        # cached_at이 없으므로 폐기

        print(
            "   ♻️ 이전 형식 캐시 삭제"
        )


        del cache[
            cache_key
        ]


        save_cache(
            cache
        )


        return None


# ==================================================
# 8. 프론트용 reachability.json 저장
# ==================================================

def save_reachability(
    start_name,
    start_lon,
    start_lat,
    search_time,
    results
):

    output = {

        "start": {

            "name":
                start_name,

            "lat":
                start_lat,

            "lon":
                start_lon
        },

        "datetime":

            search_time.strftime(
                "%Y-%m-%d %H:%M"
            ),

        "results":
            results
    }


    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )


# ==================================================
# 9. TMAP 경로 확인
# ==================================================

def check_route(
    start_lon,
    start_lat,
    end_lon,
    end_lat,
    search_time
):

    # ----------------------------------------------
    # 캐시 키 생성
    # ----------------------------------------------

    cache_key = (

        f"{start_lon},{start_lat}_"

        f"{end_lon},{end_lat}_"

        f"{search_time.strftime('%Y%m%d%H%M')}"

    )


    cache = load_cache()


    # ----------------------------------------------
    # 캐시 확인
    # ----------------------------------------------

    cached_result = (
        get_cached_result(
            cache,
            cache_key
        )
    )


    if cached_result is not None:

        return cached_result


    # ----------------------------------------------
    # API 요청 Header
    # ----------------------------------------------

    headers = {

        "Accept":
            "application/json",

        "Content-Type":
            "application/json",

        "appKey":
            APP_KEY
    }


    # ----------------------------------------------
    # API 요청 Body
    # ----------------------------------------------

    request_data = {

        "startX":
            str(start_lon),

        "startY":
            str(start_lat),

        "endX":
            str(end_lon),

        "endY":
            str(end_lat),

        # 후보 경로 최대 3개
        "count":
            3,

        "lang":
            0,

        "format":
            "json",

        "searchDttm":
            search_time.strftime(
                "%Y%m%d%H%M"
            )
    }


    # ----------------------------------------------
    # 실제 TMAP 호출
    # ----------------------------------------------

    try:

        response = requests.post(

            URL,

            headers=headers,

            json=request_data,

            timeout=10
        )


    except requests.RequestException as e:

        print(
            "   ❌ 네트워크 오류:",
            e
        )

        return None


    # ----------------------------------------------
    # 호출 한도 초과
    # ----------------------------------------------

    if response.status_code == 429:

        print(
            "   ⚠️ API 호출 한도 초과"
        )

        return None


    # ----------------------------------------------
    # 기타 API 오류
    # ----------------------------------------------

    if response.status_code != 200:

        print(
            "   ❌ API 오류:",
            response.status_code
        )

        print(
            "   ",
            response.text[:200]
        )

        return None


    # ----------------------------------------------
    # JSON 응답 읽기
    # ----------------------------------------------

    try:

        api_data = (
            response.json()
        )


    except ValueError:

        print(
            "   ❌ API 응답을 JSON으로 읽지 못했습니다."
        )

        return None


    itineraries = (

        api_data

        .get(
            "metaData",
            {}
        )

        .get(
            "plan",
            {}
        )

        .get(
            "itineraries",
            []
        )
    )


    # ==================================================
    # 10. 경로 자체가 없는 경우
    # ==================================================

    if not itineraries:

        result = {

            "reachable":
                False,

            "total_time":
                None,

            "transfers":
                None
        }


        save_result_to_cache(

            cache,
            cache_key,
            result

        )


        return result


    # ==================================================
    # 11. 후보 경로 검사
    # ==================================================

    for route in itineraries:

        reachable = True


        # ----------------------------------------------
        # 각 구간 확인
        # ----------------------------------------------

        for leg in route.get(
            "legs",
            []
        ):

            mode = (
                leg.get(
                    "mode"
                )
            )


            service = (
                leg.get(
                    "service"
                )
            )


            # 걷기 구간은 검사하지 않음
            #
            # 대중교통 구간만 확인

            if mode in [
                "SUBWAY",
                "BUS"
            ]:

                # 운행 종료
                if service == 0:

                    reachable = False

                    break


        # ----------------------------------------------
        # 가능한 후보 경로 발견
        # ----------------------------------------------

        if reachable:

            total_seconds = (
                route.get(
                    "totalTime",
                    0
                )
            )


            result = {

                "reachable":
                    True,

                "total_time":
                    round(
                        total_seconds / 60
                    ),

                "transfers":
                    route.get(
                        "transferCount",
                        0
                    )
            }


            save_result_to_cache(

                cache,
                cache_key,
                result

            )


            return result


    # ==================================================
    # 12. 모든 후보 경로가 운행 종료
    # ==================================================

    result = {

        "reachable":
            False,

        "total_time":
            None,

        "transfers":
            None
    }


    save_result_to_cache(

        cache,
        cache_key,
        result

    )


    return result


# ==================================================
# 13. 출발 장소 입력
# ==================================================

start_name = input(
    "\n출발 장소 입력: "
).strip()


if start_name not in places:

    print(
        "\n❌ 등록되지 않은 장소입니다."
    )

    print(
        "\n가능한 장소:"
    )


    for name in places:

        print(
            "-",
            name
        )


    exit()


# ==================================================
# 14. 날짜 입력
# ==================================================

date_text = input(
    "날짜 입력 (예: 20260912): "
).strip()


# ==================================================
# 15. 시간 선택
# ==================================================

print(
    "\n시간대를 선택하세요."
)


for i, time_slot in enumerate(
    TIME_SLOTS,
    start=1
):

    print(
        f"{i}. {time_slot}"
    )


try:

    time_choice = int(

        input(
            f"번호 입력 (1~{len(TIME_SLOTS)}): "
        )

    )


    if (
        time_choice < 1
        or
        time_choice > len(TIME_SLOTS)
    ):

        raise ValueError


    time_text = (
        TIME_SLOTS[
            time_choice - 1
        ]
    )


except ValueError:

    print(
        "❌ 올바른 번호를 입력하세요."
    )

    exit()


# ==================================================
# 16. 검색 시간 생성
# ==================================================

try:

    search_time = datetime.strptime(

        date_text
        +
        time_text,

        "%Y%m%d%H:%M"
    )


    # ----------------------------------------------
    # 00:00 / 00:30
    #
    # "9월 12일 밤"으로 선택한 경우
    # 실제 검색 날짜는 9월 13일
    # ----------------------------------------------

    if search_time.hour < 3:

        search_time += timedelta(
            days=1
        )


except ValueError:

    print(
        "❌ 날짜 또는 시간 형식이 잘못되었습니다."
    )

    print(
        "예: 20260912"
    )

    exit()


# ==================================================
# 17. 목적지 목록 만들기
# ==================================================

start_lon, start_lat = (
    places[start_name]
)


targets = [

    name

    for name in places

    if name != start_name

]


results = []


# ==================================================
# 18. 실행 정보 출력
# ==================================================

print(
    "\n============================"
)

print(
    "🚩 출발지:",
    start_name
)

print(
    "🕐 출발 시간:",
    search_time.strftime(
        "%Y-%m-%d %H:%M"
    )
)

print(
    "🎯 검사 목적지:",
    len(targets),
    "개"
)

print(
    "============================\n"
)


# ==================================================
# 19. 빈 결과 파일 먼저 생성
# ==================================================

save_reachability(

    start_name,

    start_lon,
    start_lat,

    search_time,

    results

)


# ==================================================
# 20. 모든 목적지 검사
# ==================================================

for index, name in enumerate(
    targets,
    start=1
):

    end_lon, end_lat = (
        places[name]
    )


    print(

        f"[{index}/{len(targets)}] "

        f"{name} 확인 중..."

    )


    route_result = check_route(

        start_lon,
        start_lat,

        end_lon,
        end_lat,

        search_time

    )


    # ----------------------------------------------
    # API 실패
    # ----------------------------------------------

    if route_result is None:

        print(
            "\n⚠️ API 호출을 중단합니다."
        )

        print(

            f"현재까지 "
            f"{len(results)}개 결과는 "
            f"저장되었습니다."

        )

        break


    # ----------------------------------------------
    # 프론트용 결과 생성
    # ----------------------------------------------

    result = {

        "name":
            name,

        "lat":
            end_lat,

        "lon":
            end_lon,

        "reachable":
            route_result[
                "reachable"
            ],

        "total_time":
            route_result[
                "total_time"
            ],

        "transfers":
            route_result[
                "transfers"
            ]
    }


    results.append(
        result
    )


    # ----------------------------------------------
    # 한 지역 끝날 때마다 바로 저장
    # ----------------------------------------------

    save_reachability(

        start_name,

        start_lon,
        start_lat,

        search_time,

        results

    )


    # ----------------------------------------------
    # 터미널 출력
    # ----------------------------------------------

    if result[
        "reachable"
    ]:

        print(

            f"   ✅ "
            f"{result['total_time']}분"
            f" / 환승 "
            f"{result['transfers']}회"

        )

    else:

        print(
            "   ❌ 도달 불가"
        )


# ==================================================
# 21. 최종 JSON 다시 저장
# ==================================================

save_reachability(

    start_name,

    start_lon,
    start_lat,

    search_time,

    results

)


# ==================================================
# 22. 결과 요약
# ==================================================

reachable_count = sum(

    1

    for result in results

    if result[
        "reachable"
    ]

)


unreachable_count = sum(

    1

    for result in results

    if not result[
        "reachable"
    ]

)


print(
    "\n============================"
)

print(
    "📊 계산 결과"
)

print(
    "============================"
)


print(

    "계산 완료:",

    len(results),

    "/",

    len(targets)

)

print("AppKey 로드:", APP_KEY[:4] + "****" + APP_KEY[-4:])
print(
    "✅ 도달 가능:",
    reachable_count
)


print(
    "❌ 도달 불가:",
    unreachable_count
)


if len(results) == len(targets):

    print(
        "🎉 모든 목적지 계산 완료"
    )

else:

    remaining = (
        len(targets)
        -
        len(results)
    )

    print(
        "⏸️ 남은 목적지:",
        remaining
    )


print(

    f"\n💾 "
    f"{OUTPUT_FILE} 저장 완료"

)