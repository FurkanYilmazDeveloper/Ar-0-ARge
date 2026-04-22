import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import requests
import shutil
import tempfile
from pathlib import Path  # Dosya yollarını yönetmek için eklendi
import pydicom
from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from typing import List, Optional
from dotenv import load_dotenv

# --- .ENV YÜKLEME (GELİŞTİRİLMİŞ) ---
# app.py'nin olduğu klasörü bul ve oradaki .env'yi yükle
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- CONFIGURATION FROM ENV ---
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")
MONGO_CLUSTER = os.getenv("MONGO_CLUSTER")
ORTHANC_URL = os.getenv("ORTHANC_URL")

# --- HATA KONTROLÜ (CRITICAL) ---
if MONGO_PASS is None:
    print(f"❌ HATA: .env dosyasından MONGO_PASS okunamadı!")
    print(f"Aranan dosya yolu: {env_path.absolute()}")
    print("Lütfen .env dosyasının 'python 3d' klasörü içinde olduğundan emin olun.")
    exit(1) # Uygulamayı durdur

def check_monai_ready():
    return True  # Always return True since MONAI is not used

# URL Encoding for MongoDB Password
encoded_pass = urllib.parse.quote_plus(MONGO_PASS)
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{encoded_pass}@{MONGO_CLUSTER}/?appName=Cluster0"
APP_SECRET = os.getenv("APP_JWT_SECRET") or MONGO_PASS or "change-this-secret"
TOKEN_EXPIRE_SECONDS = 60 * 60 * 4


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), password_hash)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def sign_token(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(APP_SECRET.encode("utf-8"), f"{header_b64}.{payload_b64}".encode("utf-8"), hashlib.sha256).digest()
    signature_b64 = b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_token(token: str) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split('.')
        signature_check = hmac.new(APP_SECRET.encode("utf-8"), f"{header_b64}.{payload_b64}".encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(signature_check, b64url_decode(signature_b64)):
            raise ValueError("Geçersiz token imzası.")

        payload = json.loads(b64url_decode(payload_b64).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("Token süresi doldu.")
        return payload
    except Exception as e:
        raise ValueError(str(e))


def create_access_token(username: str, role: str) -> str:
    payload = {"username": username, "role": role, "exp": int(time.time()) + TOKEN_EXPIRE_SECONDS}
    return sign_token(payload)


def get_token_from_header(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header bulunamadı.")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Geçersiz Authorization formatı.")
    return parts[1]


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    token = get_token_from_header(authorization)
    payload = verify_token(token)
    username = payload.get("username")
    role = payload.get("role")
    if not username or not role:
        raise HTTPException(status_code=401, detail="Geçersiz kullanıcı bilgisi.")
    return {"username": username, "role": role}


def create_default_users(users_collection):
    try:
        users_collection.create_index("username", unique=True)
    except Exception:
        pass

    if users_collection.count_documents({}) == 0:
        users_collection.insert_many([
            {"username": "admin", "password_hash": hash_password("admin123"), "role": "admin"},
            {"username": "doktor", "password_hash": hash_password("doktor123"), "role": "doctor", "allowed_organ": "Liver"}
        ])
        print("✅ Varsayılan kullanıcılar oluşturuldu: admin/admin123, doktor/doktor123")

try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["doktor_paneli"]
    hastalar_col = db["patients"]
    users_col = db["users"]
    mongo_client.admin.command('ping')
    create_default_users(users_col)
    print("✅ MongoDB Atlas Bağlantısı Başarılı! (Connected via .env)")
except Exception as e:
    print(f"❌ MongoDB Bağlantı Hatası: {e}")

ORGAN_MAP = {
    1: ('Spleen', '#3b82f6'),
    2: ('R-Kidney', '#10b981'),
    3: ('L-Kidney', '#059669'),
    4: ('Gallbladder', '#84cc16'),
    5: ('Liver', '#ef4444'),
    6: ('Stomach', '#f97316'),
    7: ('Aorta', '#dc2626'),
    8: ('IVC', '#7c3aed'),
    9: ('Portal Vein', '#2563eb'),
    10: ('Pancreas', '#facc15'),
    11: ('R-Adrenal', '#a855f7'),
    12: ('L-Adrenal', '#9333ea'),
    13: ('Lung LUL', '#60a5fa'),
    14: ('Lung LLL', '#1d4ed8'),
    15: ('Lung RUL', '#86efac'),
    16: ('Lung RML', '#34d399'),
    17: ('Lung RLL', '#065f46'),
    42: ('Esophagus', '#f472b6'),
    43: ('Trachea', '#e879f9'),
    44: ('Myocardium', '#b91c1c'),
    45: ('LA', '#fb7185'),
    46: ('LV', '#ef4444'),
    47: ('RA', '#fca5a5'),
    48: ('RV', '#fecaca'),
    49: ('Pulmonary Artery', '#0ea5e9')
}

# DICOM Body Part to Organ mapping
BODY_PART_TO_ORGAN = {
    'ABDOMEN': 'Abdomen',  # Karın bölgesi
    'CHEST': 'Chest',     # Göğüs bölgesi
    'HEAD': 'Head',       # Baş bölgesi
    'PELVIS': 'Abdomen',  # Pelvis'i karın olarak kabul et
    'NECK': 'Chest',      # Boyun'u göğüs olarak kabul et
    'SPINE': 'Chest',     # Omurga'yı göğüs olarak kabul et
    'EXTREMITY': 'Abdomen',  # Placeholder
    'WHOLEBODY': 'Abdomen'   # Placeholder
}

def detect_organ_from_dicom(file_path: str) -> str:
    """DICOM dosyasından organ tespit et."""
    try:
        ds = pydicom.dcmread(file_path)
        body_part = getattr(ds, 'BodyPartExamined', None)
        if body_part and body_part.upper() in BODY_PART_TO_ORGAN:
            return BODY_PART_TO_ORGAN[body_part.upper()]
        # Eğer body part yok veya eşleşmezse, default olarak Liver döndür (ama aslında None döndürmek daha iyi)
        return None
    except Exception as e:
        print(f"DICOM organ tespiti hatası: {e}")
        return None

@app.post("/login")
async def login(credentials: dict):
    username = credentials.get("username")
    password = credentials.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Kullanıcı adı ve şifre gereklidir.")

    user = users_col.find_one({"username": username})
    if not user or not verify_password(password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre yanlış.")

    access_token = create_access_token(username=username, role=user.get("role", "doctor"))
    return {"access_token": access_token, "token_type": "bearer", "role": user.get("role", "doctor"), "username": username}

@app.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    user = get_user(current_user["username"])
    return {
        "username": current_user["username"],
        "role": current_user["role"],
        "allowed_organ": user.get("allowed_organ")
    }


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Yalnızca admin erişebilir.")
    return current_user


def get_user(username: str) -> dict:
    return users_col.find_one({"username": username}) or {}


@app.get("/settings")
async def get_settings(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") == "admin":
        docs = list(users_col.find({"role": "doctor"}, {"_id": 0, "username": 1, "allowed_organ": 1}))
        return {"role": "admin", "doctors": docs}

    user = get_user(current_user["username"])
    return {"role": "doctor", "allowed_organ": user.get("allowed_organ", "Abdomen"), "username": current_user["username"]}


@app.post("/settings/allowed-organ")
async def update_allowed_organ(data: dict, current_user: dict = Depends(require_admin)):
    target_username = data.get("username")
    allowed_organ = data.get("allowed_organ")
    if not target_username or not allowed_organ:
        raise HTTPException(status_code=400, detail="username ve allowed_organ gerekli.")

    user = get_user(target_username)
    if not user or user.get("role") != "doctor":
        raise HTTPException(status_code=404, detail="Doktor bulunamadı.")

    users_col.update_one(
        {"username": target_username},
        {"$set": {"allowed_organ": allowed_organ}}
    )
    return {"status": "success", "username": target_username, "allowed_organ": allowed_organ}


@app.post("/doctors")
async def create_doctor(data: dict, current_user: dict = Depends(require_admin)):
    username = data.get("username")
    password = data.get("password")
    allowed_organ = data.get("allowed_organ", "Abdomen")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username ve password gerekli.")

    if users_col.find_one({"username": username}):
        raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten var.")

    users_col.insert_one({
        "username": username,
        "password_hash": hash_password(password),
        "role": "doctor",
        "allowed_organ": allowed_organ
    })
    return {"status": "success", "username": username, "allowed_organ": allowed_organ}


# --- 1. PATIENT UPLOAD ---
@app.post("/upload-patient")
async def upload_patient(
    files: List[UploadFile] = File(...),
    name: str = Form(...),
    organ: str = Form(None),
    gender: str = Form(None),
    age: str = Form(None),
    scan_date: str = Form(None),
    current_user: dict = Depends(get_current_user)
):
    patient_uuid = None
    upload_count = 0
    uploader = current_user.get("username")
    detected_organ = None

    if current_user.get("role") == "doctor":
        user = get_user(uploader)
        allowed_organ = user.get("allowed_organ")
        if not allowed_organ:
            raise HTTPException(status_code=403, detail="Lütfen önce bir organ atanmış bir doktor hesabıyla giriş yapın.")
        patient_organ = None  # Doktorlar serbestçe yükleyebilir, organ kısıtlaması kaldırıldı

    elif current_user.get("role") == "admin":
        # Admin için form'dan organ al
        if not organ:
            raise HTTPException(status_code=400, detail="Admin olarak yükleme yaparken organ seçmeniz gereklidir.")
        patient_organ = organ
    else:
        raise HTTPException(status_code=403, detail="Geçersiz rol.")

    try:
        for file in files:
            # Sadece DICOM uzantılı dosyaları işle
            if not file.filename.lower().endswith(('.dcm', '.dicom')):
                continue  # DICOM olmayan dosyaları atla
            
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                shutil.copyfileobj(file.file, temp_file)
                temp_path = temp_file.name
            try:
                with open(temp_path, "rb") as f:
                    orthanc_res = requests.post(
                        f"{ORTHANC_URL}/instances", 
                        data=f.read(),
                        auth=('orthanc', 'orthanc')
                    ).json()
                if not patient_uuid:
                    patient_uuid = orthanc_res['ParentPatient']
                upload_count += 1
            finally:
                if os.path.exists(temp_path): os.remove(temp_path)

        if not patient_uuid:
            raise Exception("Geçerli DICOM dosyası bulunamadı. Sadece .dcm veya .dicom uzantılı dosyalar yüklenebilir.")

        update_data = {
            "name": name,
            "orthanc_id": patient_uuid,
            "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "uploader": uploader
        }
        if patient_organ:
            update_data["allowed_organ"] = patient_organ
        if gender:
            update_data["gender"] = gender
        if age:
            update_data["age"] = age
        if scan_date:
            update_data["scan_date"] = scan_date

        hastalar_col.update_one(
            {"orthanc_id": patient_uuid},
            {
                "$set": update_data,
                "$setOnInsert": {"createdAt": time.strftime("%Y-%m-%d %H:%M:%S")}
            },
            upsert=True
        )
        return {"status": "success", "uuid": patient_uuid, "files_uploaded": upload_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- 2. GET PATIENTS ---
@app.get("/patients")
async def get_patients(current_user: dict = Depends(get_current_user)):
    try:
        query = {}
        if current_user.get("role") == "doctor":
            user = get_user(current_user["username"])
            allowed_organ = user.get("allowed_organ")
            query = {"$or": [{"uploader": current_user["username"]}]}
            if allowed_organ:
                query["$or"].append({"allowed_organ": allowed_organ})
        docs = list(hastalar_col.find(query).sort("createdAt", -1))
        return [{
            "uuid": d.get("orthanc_id") or str(d.get("_id")),
            "display": d.get("name") or "İsimsiz",
            "gender": d.get("gender", ""),
            "age": d.get("age", ""),
            "scan_date": d.get("scan_date", ""),
            "orthanc_id": d.get("orthanc_id", "")
        } for d in docs]
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching patients: {e}")
        return []

# --- 3. GET PATIENT SLICES (DICOM Slicer) ---
@app.get("/patient/{patient_uuid}/slices")
async def get_patient_slices(patient_uuid: str, current_user: dict = Depends(get_current_user)):
    """Orthanc'taki hastanın kesit görüntülerini base64 JPEG olarak döner."""
    try:
        # Orthanc'tan hastanın study'lerini al
        patient_res = requests.get(
            f"{ORTHANC_URL}/patients/{patient_uuid}",
            auth=('orthanc', 'orthanc'),
            timeout=10
        )
        if patient_res.status_code != 200:
            raise HTTPException(status_code=404, detail="Hasta Orthanc'ta bulunamadı.")
        
        patient_data = patient_res.json()
        studies = patient_data.get("Studies", [])
        
        if not studies:
            return {"slices": [], "total": 0}
        
        # İlk study'den series'leri al
        all_instances = []
        for study_id in studies:
            study_res = requests.get(
                f"{ORTHANC_URL}/studies/{study_id}",
                auth=('orthanc', 'orthanc'),
                timeout=10
            ).json()
            for series_id in study_res.get("Series", []):
                series_res = requests.get(
                    f"{ORTHANC_URL}/series/{series_id}",
                    auth=('orthanc', 'orthanc'),
                    timeout=10
                ).json()
                all_instances.extend(series_res.get("Instances", []))
        
        if not all_instances:
            return {"slices": [], "total": 0}
        
        # Instance'ları sıralamak için instance number'ları al
        instance_info = []
        for inst_id in all_instances:
            try:
                tags_res = requests.get(
                    f"{ORTHANC_URL}/instances/{inst_id}/simplified-tags",
                    auth=('orthanc', 'orthanc'),
                    timeout=5
                ).json()
                instance_number = int(tags_res.get("InstanceNumber", 0))
                instance_info.append({"id": inst_id, "number": instance_number})
            except Exception:
                instance_info.append({"id": inst_id, "number": 0})
        
        # Instance number'a göre sırala
        instance_info.sort(key=lambda x: x["number"])
        
        # Her instance için preview al ve base64'e çevir
        slices = []
        for info in instance_info:
            try:
                img_res = requests.get(
                    f"{ORTHANC_URL}/instances/{info['id']}/preview",
                    auth=('orthanc', 'orthanc'),
                    timeout=10
                )
                if img_res.status_code == 200:
                    img_b64 = base64.b64encode(img_res.content).decode('utf-8')
                    content_type = img_res.headers.get('Content-Type', 'image/png')
                    slices.append({
                        "data": f"data:{content_type};base64,{img_b64}",
                        "instance_number": info["number"]
                    })
            except Exception as e:
                print(f"Slice yükleme hatası (instance {info['id']}): {e}")
                continue
        
        return {"slices": slices, "total": len(slices)}
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Slice endpoint hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Kesit görüntüleri yüklenemedi: {str(e)}")


# --- 4. DELETE PATIENT (Sadece Admin) ---
@app.delete("/patient/{patient_uuid}")
async def delete_patient(patient_uuid: str, current_user: dict = Depends(get_current_user)):
    from bson import ObjectId
    
    # Sadece admin silebilsin
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Yalnızca admin hastayı silebilir.")
    
    try:
        # 1. MONGODB'den Sil
        res = hastalar_col.delete_one({"orthanc_id": patient_uuid})
        
        # Eğer orthanc_id ile bulunamadıysa, belki bu UUID aslında MongoDB'nin _id'sidir.
        if res.deleted_count == 0:
            if len(patient_uuid) == 24: # Valid ObjectId length
                res = hastalar_col.delete_one({"_id": ObjectId(patient_uuid)})

        if res.deleted_count == 0:
             raise HTTPException(status_code=404, detail="Hasta MongoDB'de bulunamadı (UUID veya ID eşleşmedi).")
             
        # 2. ORTHANC'tan Sil (DICOM görüntülerini silmek için) - sadece orthanc_id geçerliyse deneriz
        if len(patient_uuid) != 24:
            try:
                requests.delete(f"{ORTHANC_URL}/patients/{patient_uuid}", auth=('orthanc', 'orthanc'), timeout=3)
            except Exception as e:
                print(f"Orthanc silme hatası (göz ardı ediliyor): {e}")
                pass
            
        return {"status": "success", "message": "Hasta başarıyla silindi"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)