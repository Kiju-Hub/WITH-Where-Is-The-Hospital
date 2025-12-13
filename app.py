from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import csv
import os
import math
import requests
import xmltodict
from dotenv import load_dotenv
from datetime import datetime
from openai import OpenAI
from urllib.parse import unquote

# ================================
# 초기 설정
# ================================
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = Flask(__name__)
CORS(app)

CSV_FILE = os.path.join(os.path.dirname(__file__), "data", "hospitals.csv")

PUBLIC_KEY = os.getenv("PUBLIC_DATA_API_KEY")
KAKAO_KEY = os.getenv("KAKAO_MAP_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PHARMACY_KEY = os.getenv("PHARMACY_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# ================================
# 공통 함수
# ================================
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def safe_float(val):
    try:
        if val is None:
            return None
        v = str(val).strip()
        if v == "":
            return None
        return float(v)
    except:
        return None

# ================================
# STAGE1 후보 자동 선정 (핵심)
# ================================
def pick_stage1_candidates(lat, lon):
    candidates = set()

    # 수도권
    if 36.5 <= lat <= 38.5:
        if lon < 127.0:
            candidates.update(["서울특별시", "인천광역시", "경기도"])
        else:
            candidates.update(["서울특별시", "경기도"])

    # 충청
    if 36.0 <= lat < 36.5:
        if lon < 127.0:
            candidates.update(["충청남도", "대전광역시", "세종특별자치시"])
        else:
            candidates.update(["충청북도", "세종특별자치시"])

    # 전라
    if 34.5 <= lat < 36.0:
        candidates.update(["전라북도", "전라남도", "광주광역시"])

    # 경상
    if lat < 34.5:
        if lon < 128.0:
            candidates.update(["경상남도", "부산광역시", "울산광역시"])
        else:
            candidates.update(["경상북도", "대구광역시"])

    # 제주
    if lat < 34.0 and lon < 127.0:
        candidates.add("제주특별자치도")

    return list(candidates)


# ================================
# 병원 좌표 CSV → 메모리 캐시
# ================================
HOSPITAL_COORDS = {}

try:
    with open(CSV_FILE, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                if r.get("좌표(Y)") and r.get("좌표(X)"):
                    HOSPITAL_COORDS[r["요양기관명"]] = {
                        "lat": float(r["좌표(Y)"]),
                        "lng": float(r["좌표(X)"]),
                        "addr": r["주소"],
                        "phone": r["전화번호"]
                    }
            except:
                continue
except:
    print("⚠ 병원 CSV 로딩 실패")

# ================================
# 메인 페이지
# ================================
@app.route("/")
def home():
    return render_template("index.html", kakao_key=KAKAO_KEY)

# ================================
# [API] 병원 검색 (CSV 기반 유지)
# ================================
@app.route("/api/hospitals")
def get_hospitals():
    user_lat = request.args.get("lat", type=float)
    user_lon = request.args.get("lon", type=float)
    radius_km = request.args.get("radius", default=3.0, type=float)
    
    # 1. 프론트엔드에서 보낸 검색어(예: "내과")를 받습니다.
    keyword = request.args.get("keyword", default="", type=str) 

    result = []
    for name, c in HOSPITAL_COORDS.items():
        # 2. 검색어 필터링 로직 추가
        # 키워드가 존재하는데, 병원 이름(name)에 키워드가 없다면 건너뜁니다.
        if keyword and (keyword not in name):
            continue

        dist = calculate_distance(user_lat, user_lon, c["lat"], c["lng"])
        if dist <= radius_km:
            result.append({
                "name": name,
                "address": c["addr"],
                "phone": c["phone"],
                "lat": c["lat"],
                "lng": c["lng"],
                "distance": round(dist, 2)
            })

    result.sort(key=lambda x: x["distance"])
    return jsonify(result)

# ================================
# [API] 응급실 (위치 기반 + 거리 기준)
# ================================
@app.route("/api/emergency")
def get_emergency():
    user_lat = request.args.get("lat", type=float)
    user_lon = request.args.get("lon", type=float)
    radius_km = request.args.get("radius", default=20.0, type=float)

    url = "http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEmrrmRltmUsefulSckbdInfoInqire"

    stage1_list = pick_stage1_candidates(user_lat, user_lon)
    all_items = []

    for stage1 in stage1_list:
        params = {
            "serviceKey": unquote(PUBLIC_KEY),
            "STAGE1": stage1,
            "numOfRows": "200"
        }
        try:
            response = requests.get(url, params=params, timeout=3)
            data = xmltodict.parse(response.content)
            items = data["response"]["body"]["items"]
            if items and "item" in items:
                chunk = items["item"]
                if isinstance(chunk, list):
                    all_items.extend(chunk)
                else:
                    all_items.append(chunk)
        except:
            continue

    result = []
    for item in all_items:
        name = item.get("dutyName")
        if name not in HOSPITAL_COORDS:
            continue

        c = HOSPITAL_COORDS[name]
        dist = calculate_distance(user_lat, user_lon, c["lat"], c["lng"])

        if dist <= radius_km:
            result.append({
                "name": name,
                "address": c["addr"],
                "phone": item.get("dutyTel3"),
                "lat": c["lat"],
                "lng": c["lng"],
                "distance": round(dist, 2),
                "available": int(item.get("hvec", 0)),
                "status": "가능" if int(item.get("hvec", 0)) > 0 else "불가"
            })

    result.sort(key=lambda x: (x["status"] == "불가", x["distance"]))
    return jsonify(result[:20])

#=================================
# [약국데이터]

# ================================
# [API] 약국 검색 (공공데이터 API 연동)
# ================================
# ================================
# [API] 약국 검색 (반경 필터링 적용)
# ================================
@app.route("/api/pharmacy")
def get_pharmacy():
    user_lat = request.args.get("lat", type=float)
    user_lon = request.args.get("lon", type=float)
    # 1. 반경(radius) 파라미터를 받습니다. (기본값 3km)
    radius_km = request.args.get("radius", default=3.0, type=float)
    
    # 약국 정보 조회 API URL (국립중앙의료원)
    url = "http://apis.data.go.kr/B552657/ErmctInsttInfoInqireService/getParmacyLcinfoInqire"

    params = {
        "serviceKey": unquote(PHARMACY_KEY), 
        "WGS84_LON": user_lon,
        "WGS84_LAT": user_lat,
        "numOfRows": "100",  # 반경 내 필터링을 위해 넉넉하게 가져옵니다
        "pageNo": "1"
    }

    response = requests.get(url, params=params)
    result = []

    try:
        data = xmltodict.parse(response.content)
        
        if "response" in data and "body" in data["response"] and "items" in data["response"]["body"]:
            items = data["response"]["body"]["items"]
            if items:
                # 결과가 1개일 경우 리스트가 아니라 딕셔너리로 오므로 리스트로 감싸줌
                pharmacy_list = items["item"] if isinstance(items["item"], list) else [items["item"]]

                for item in pharmacy_list:
                    p_lat = safe_float(item.get("latitude"))
                    p_lon = safe_float(item.get("longitude"))
                    
                    if p_lat and p_lon:
                        # 2. 거리 계산
                        dist = calculate_distance(user_lat, user_lon, p_lat, p_lon)
                        
                        # 3. 설정한 반경(radius_km) 이내인 경우에만 결과에 추가
                        if dist <= radius_km:
                            result.append({
                                "name": item.get("dutyName"),
                                "address": item.get("dutyAddr"),
                                "phone": item.get("dutyTel1"),
                                "lat": p_lat,
                                "lng": p_lon,
                                "distance": round(dist, 2),
                                "startTime": item.get("startTime", "정보없음"),
                                "endTime": item.get("endTime", "정보없음")
                            })
    except Exception as e:
        print(f"약국 API 에러: {e}")

    # 거리순 정렬
    result.sort(key=lambda x: x["distance"])
    
    return jsonify(result)
#=================================

# ================================
# [API] AI 챗봇
# ================================
@app.route("/api/chat", methods=["POST"])
def chat_bot():
    data = request.json
    user_message = data.get("message")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "증상에 맞는 진료과를 추천하고 마지막에 '정확한 진단은 병원을 방문하세요.'로 끝내라"},
            {"role": "user", "content": user_message}
        ]
    )
    return jsonify({"reply": response.choices[0].message.content})

# ================================
# 서버 실행
# ================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
