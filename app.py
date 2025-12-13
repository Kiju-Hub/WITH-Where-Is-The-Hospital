from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import os
import math
import requests
import xmltodict
import pymysql
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
app.config['JSON_AS_ASCII'] = False  # <--- 이 줄 추가 (한글이 제대로 보이게 함)
CORS(app)

# ================================
# 환경 변수 로드
# ================================
PUBLIC_KEY = os.getenv("PUBLIC_DATA_API_KEY")
KAKAO_KEY = os.getenv("KAKAO_MAP_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PHARMACY_KEY = os.getenv("PHARMACY_API_KEY")
KAKAO_REST_KEY = os.getenv("KAKAO_REST_KEY")
# MySQL 환경 변수
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

client = OpenAI(api_key=OPENAI_API_KEY)

# ================================
# DB 연결 함수
# ================================
def get_db():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

# ================================
# 공통 함수
# ================================
def calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine 거리 계산 (km)"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def safe_float(val):
    """공공데이터 null/빈값 방어"""
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
# STAGE1 후보 자동 선정 (기존 로직 유지)
# ================================
def pick_stage1_candidates(lat, lon):
    candidates = set()

    if 36.5 <= lat <= 38.5:
        candidates.update(["서울특별시", "인천광역시", "경기도"])

    if 36.0 <= lat < 36.5:
        candidates.update(["충청남도", "충청북도", "대전광역시", "세종특별자치시"])

    if 34.5 <= lat < 36.0:
        candidates.update(["전라북도", "전라남도", "광주광역시"])

    if lat < 34.5:
        candidates.update(["경상북도", "경상남도", "부산광역시", "대구광역시", "울산광역시"])

    if lat < 34.0 and lon < 127.0:
        candidates.add("제주특별자치도")

    return list(candidates)

# ================================
# 메인 페이지
# ================================
@app.route("/")
def home():
    return render_template("index.html", kakao_key=KAKAO_KEY)

# ================================
# [API] 병원 검색 (CSV ❌ → MySQL ✅)
# ================================
# ================================
# [API] 병원 검색 (한글 DB 컬럼 대응 버전)
# ================================
# ================================
# [API] 병원 검색 (영어 DB 컬럼 버전 - 최종)
# ================================
# ================================
# [API] 병원 검색 (최종 정상화 버전)
# ================================
@app.route("/api/hospitals")
def get_hospitals():
    user_lat = request.args.get("lat", type=float)
    user_lon = request.args.get("lon", type=float)
    radius_km = request.args.get("radius", default=3.0, type=float)
    keyword = request.args.get("keyword", default="", type=str)

    if user_lat is None or user_lon is None:
        return jsonify({"error": "위치 정보가 필요합니다."}), 400

    conn = get_db()
    result = []

    try:
        with conn.cursor() as cur:
            # 1. 내 주변에서 가장 가까운 병원 1개를 먼저 찾아봅니다 (거리 무제한)
            # 데이터가 시흥 근처에 아예 없는지 확인하기 위함입니다.
            check_sql = """
            SELECT name, y_pos, x_pos,
                (6371 * acos(cos(radians(%s)) * cos(radians(y_pos)) * cos(radians(x_pos) - radians(%s)) + sin(radians(%s)) * sin(radians(y_pos)))) AS dist
            FROM hospitals
            WHERE name LIKE %s
            ORDER BY dist ASC
            LIMIT 1
            """
            cur.execute(check_sql, (user_lat, user_lon, user_lat, f"%{keyword}%"))
            closest = cur.fetchone()
            
            if closest:
                print(f"👀 [진단] 가장 가까운 병원: {closest['name']} (거리: {round(closest['dist'], 2)}km)")
            else:
                print(f"⚠️ [진단] '{keyword}' 검색 결과가 DB 전체에 없습니다.")

            # 2. 실제 반경 내 검색 (정석 로직: y_pos=위도, x_pos=경도)
            sql = """
            SELECT 
                name, 
                addr AS address, 
                tel_no AS phone, 
                y_pos AS lat,   -- y_pos는 위도(Latitude)
                x_pos AS lng,   -- x_pos는 경도(Longitude)
                (
                    6371 * acos(
                        LEAST(1.0, GREATEST(-1.0, 
                            cos(radians(%s)) * cos(radians(y_pos)) * cos(radians(x_pos) - radians(%s)) + 
                            sin(radians(%s)) * sin(radians(y_pos))
                        ))
                    )
                ) AS distance
            FROM hospitals
            WHERE name LIKE %s
            HAVING distance <= %s
            ORDER BY distance
            LIMIT 50
            """
            
            cur.execute(sql, (
                user_lat, user_lon, user_lat, 
                f"%{keyword}%", 
                radius_km
            ))
            result = cur.fetchall()
            print(f"🔍 최종 결과 반환 수: {len(result)}개")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        return jsonify({"error": str(e)}), 500
        
    finally:
        conn.close()

    return jsonify(result)

# ================================
# [API] 응급실 (기존 로직 유지 + DB 좌표 매칭)
# ================================
@app.route("/api/emergency")
def get_emergency():
    user_lat = request.args.get("lat", type=float)
    user_lon = request.args.get("lon", type=float)
    radius_km = request.args.get("radius", default=20.0, type=float)

    url = "http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEmrrmRltmUsefulSckbdInfoInqire"
    stage1_list = pick_stage1_candidates(user_lat, user_lon)

    conn = get_db()
    result = []

    try:
        with conn.cursor() as cur:
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
                        item_list = items["item"] if isinstance(items["item"], list) else [items["item"]]

                        for item in item_list:
                            name = item.get("dutyName")

                            # 병원 이름으로 DB 좌표 조회
                            cur.execute("""
                                SELECT y_pos AS lat, x_pos AS lng, addr
                                FROM hospitals
                                WHERE name = %s
                                LIMIT 1
                            """, (name,))
                            row = cur.fetchone()
                            if not row:
                                continue

                            dist = calculate_distance(user_lat, user_lon, row["lat"], row["lng"])
                            if dist <= radius_km:
                                result.append({
                                    "name": name,
                                    "address": row["addr"],
                                    "phone": item.get("dutyTel3"),
                                    "lat": row["lat"],
                                    "lng": row["lng"],
                                    "distance": round(dist, 2),
                                    "available": int(item.get("hvec", 0)),
                                    "status": "가능" if int(item.get("hvec", 0)) > 0 else "불가"
                                })
                except:
                    continue
    finally:
        conn.close()

    result.sort(key=lambda x: (x["status"] == "불가", x["distance"]))
    return jsonify(result[:20])

# ================================
# [API] 약국 (기존 로직 유지)
# ================================
# ================================
# [API] 약국 검색 (카카오 로컬 API 사용 - 정확도 100%)
# ================================
@app.route("/api/pharmacy")
def get_pharmacy():
    user_lat = request.args.get("lat", type=float)
    user_lon = request.args.get("lon", type=float)
    radius_km = request.args.get("radius", default=3.0, type=float)
    
    # 1. 좌표 유효성 검사
    if user_lat is None or user_lon is None:
        return jsonify([])

    # 2. 카카오 API 설정 (PM9: 약국 카테고리 코드)
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {
        "Authorization": f"KakaoAK {KAKAO_REST_KEY}"  # .env의 REST API 키 사용
    }
    params = {
        "category_group_code": "PM9",  # 약국
        "x": user_lon,                 # 경도
        "y": user_lat,                 # 위도
        "radius": int(radius_km * 1000), # m 단위 변환
        "sort": "distance"             # 거리순
    }

    result = []
    try:
        # 3. 카카오 서버로 요청
        response = requests.get(url, headers=headers, params=params, timeout=5)
        
        # 4. 응답 성공 시 데이터 파싱
        if response.status_code == 200:
            data = response.json()
            items = data.get("documents", [])
            
            for item in items:
                result.append({
                    "name": item.get("place_name"),
                    "address": item.get("road_address_name") or item.get("address_name"),
                    "phone": item.get("phone"),
                    "lat": float(item.get("y")),
                    "lng": float(item.get("x")),
                    "distance": round(float(item.get("distance")) / 1000, 2), # m -> km
                    "status": "운영중" # 카카오는 운영 상태를 안 줘서 기본값 처리
                })
        else:
            print(f"❌ 카카오 API 오류: {response.status_code}, {response.text}")
            
    except Exception as e:
        print(f"❌ 약국 검색 중 에러: {e}")

    # 거리순 정렬
    result.sort(key=lambda x: x["distance"])
    
    return jsonify(result)

# ================================
# [API] AI 챗봇 (기존 유지)
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
