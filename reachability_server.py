import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
PLACES_FILE = BASE_DIR / "places.json"
CACHE_FILE = BASE_DIR / "route_cache.json"

TMAP_URL = "https://apis.openapi.sk.com/transit/routes"
CACHE_TTL_HOURS = 24

load_dotenv(BASE_DIR / ".env")

APP_KEY = os.getenv("SK_APP_KEY")
if not APP_KEY:
    raise RuntimeError("환경변수 SK_APP_KEY가 없습니다. .env 파일을 확인하세요.")

app = FastAPI(title="Night Seoul Reachability API")


class ReachabilityRequest(BaseModel):
    date: str
    time: str
    start_name: str | None = None
    start_lat: float | None = None
    start_lon: float | None = None


def load_places():
    if not PLACES_FILE.exists():
        raise RuntimeError("places.json 파일을 찾을 수 없습니다.")

    with open(PLACES_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    result = {}

    if isinstance(raw, list):
        for item in raw:
            name = item["name"]
            lat = item.get("lat")
            lon = item.get("lon", item.get("lng"))
            result[name] = {
                "name": name,
                "lat": float(lat),
                "lon": float(lon)
            }
        return result

    if isinstance(raw, dict):
        for name, value in raw.items():
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                result[name] = {
                    "name": name,
                    "lon": float(value[0]),
                    "lat": float(value[1])
                }
            elif isinstance(value, dict):
                result[name] = {
                    "name": name,
                    "lon": float(value.get("lon", value.get("lng"))),
                    "lat": float(value["lat"])
                }
        return result

    raise RuntimeError("places.json 형식을 이해할 수 없습니다.")


PLACES = load_places()


def load_cache():
    if not CACHE_FILE.exists():
        return {}

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


route_cache = load_cache()
cache_lock = Lock()


def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(route_cache, f, ensure_ascii=False, indent=2)


def make_cache_key(start_lon, start_lat, end_lon, end_lat, search_dt):
    return "|".join([
        f"{start_lon:.6f}",
        f"{start_lat:.6f}",
        f"{end_lon:.6f}",
        f"{end_lat:.6f}",
        search_dt.strftime("%Y%m%d%H%M")
    ])


def get_cached_result(key):
    with cache_lock:
        item = route_cache.get(key)

        if not item:
            return None

        try:
            cached_at = datetime.fromisoformat(item["cached_at"])
        except Exception:
            route_cache.pop(key, None)
            return None

        if datetime.now() - cached_at >= timedelta(hours=CACHE_TTL_HOURS):
            route_cache.pop(key, None)
            return None

        return item.get("result")


def save_cached_result(key, result):
    with cache_lock:
        route_cache[key] = {
            "cached_at": datetime.now().isoformat(timespec="seconds"),
            "result": result
        }

        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(route_cache, f, ensure_ascii=False, indent=2)


def check_route(start_lon, start_lat, end_lon, end_lat, search_dt):
    key = make_cache_key(
        start_lon, start_lat,
        end_lon, end_lat,
        search_dt
    )

    cached = get_cached_result(key)
    if cached is not None:
        return cached

    payload = {
        "startX": str(start_lon),
        "startY": str(start_lat),
        "endX": str(end_lon),
        "endY": str(end_lat),
        "count": 3,
        "searchDttm": search_dt.strftime("%Y%m%d%H%M")
    }

    headers = {
        "appKey": APP_KEY,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            TMAP_URL,
            headers=headers,
            json=payload,
            timeout=20
        )
    except requests.RequestException as e:
        raise RuntimeError(f"TMAP 요청 실패: {e}")

    if response.status_code == 429:
        raise RuntimeError("TMAP API 요청 한도 또는 호출 제한에 걸렸습니다.")

    if response.status_code != 200:
        raise RuntimeError(
            f"TMAP API 오류 ({response.status_code}): {response.text[:200]}"
        )

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError("TMAP 응답을 JSON으로 읽지 못했습니다.")

    itineraries = (
        data
        .get("metaData", {})
        .get("plan", {})
        .get("itineraries", [])
    )

    if not itineraries:
        result = {
            "reachable": False,
            "total_time": None,
            "transfers": None
        }
        save_cached_result(key, result)
        return result

    usable_routes = []

    for itinerary in itineraries:
        usable = True

        for leg in itinerary.get("legs", []):
            mode = leg.get("mode")

            if mode in ("BUS", "SUBWAY") and leg.get("service") == 0:
                usable = False
                break

        if usable:
            usable_routes.append(itinerary)

    if not usable_routes:
        result = {
            "reachable": False,
            "total_time": None,
            "transfers": None
        }
        save_cached_result(key, result)
        return result

    best = min(
        usable_routes,
        key=lambda route: route.get("totalTime", 10**12)
    )

    result = {
        "reachable": True,
        "total_time": round(best.get("totalTime", 0) / 60),
        "transfers": best.get("transferCount", 0)
    }

    save_cached_result(key, result)
    return result


def make_search_datetime(date_text, time_text):
    try:
        search_dt = datetime.strptime(
            f"{date_text} {time_text}",
            "%Y-%m-%d %H:%M"
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="날짜 또는 시각 형식이 잘못되었습니다."
        )

    # 심야 UI에서 00:00 / 00:30은 선택 날짜의 다음 날로 해석
    if search_dt.hour < 3:
        search_dt += timedelta(days=1)

    return search_dt


@app.get("/health")
def health():
    return {
        "ok": True,
        "places": len(PLACES)
    }


@app.post("/api/reachability")
def calculate_reachability(req: ReachabilityRequest):
    search_dt = make_search_datetime(req.date, req.time)

    if (
        req.start_name
        and req.start_name != "내 현재 위치"
        and req.start_name in PLACES
    ):
        start_place = PLACES[req.start_name]
        start_name = start_place["name"]
        start_lat = start_place["lat"]
        start_lon = start_place["lon"]

    elif req.start_lat is not None and req.start_lon is not None:
        start_name = req.start_name or "내 현재 위치"
        start_lat = float(req.start_lat)
        start_lon = float(req.start_lon)

    else:
        raise HTTPException(
            status_code=400,
            detail="출발지를 찾을 수 없습니다."
        )

    # 동시에 너무 많은 요청을 보내면 API 제한/불안정 가능성이 있으므로
    # 8개까지만 병렬 처리한다.
    targets = [
        (name, destination)
        for name, destination in PLACES.items()
        if not (start_name in PLACES and name == start_name)
    ]

    results_by_name = {}

    def calculate_one(name, destination):
        route = check_route(
            start_lon=start_lon,
            start_lat=start_lat,
            end_lon=destination["lon"],
            end_lat=destination["lat"],
            search_dt=search_dt
        )

        return {
            "name": name,
            "lat": destination["lat"],
            "lon": destination["lon"],
            "reachable": route["reachable"],
            "total_time": route["total_time"],
            "transfers": route["transfers"]
        }

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_map = {
                executor.submit(calculate_one, name, destination): name
                for name, destination in targets
            }

            for future in as_completed(future_map):
                name = future_map[future]
                results_by_name[name] = future.result()

    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"병렬 계산 중 오류: {e}"
        )

    # 병렬 처리하면 완료 순서는 뒤섞이므로,
    # places.json 원래 순서대로 다시 정렬해서 프론트에 반환한다.
    results = [
        results_by_name[name]
        for name, _ in targets
        if name in results_by_name
    ]

    return {
        "start": {
            "name": start_name,
            "lat": start_lat,
            "lon": start_lon
        },
        "datetime": search_dt.strftime("%Y-%m-%d %H:%M"),
        "results": results
    }


@app.get("/")
def root():
    index_file = BASE_DIR / "index.html"

    if not index_file.exists():
        raise HTTPException(
            status_code=404,
            detail="index.html 파일이 없습니다."
        )

    return FileResponse(index_file)


@app.get("/index.html")
def index():
    return root()
