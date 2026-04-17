import os, time, requests, shutil, tempfile, urllib.parse, subprocess
from pathlib import Path  # Dosya yollarını yönetmek için eklendi
import nibabel as nib, pyvista as pv, numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from typing import List
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
MONAI_URL = os.getenv("MONAI_URL")

# --- HATA KONTROLÜ (CRITICAL) ---
if MONGO_PASS is None:
    print(f"❌ HATA: .env dosyasından MONGO_PASS okunamadı!")
    print(f"Aranan dosya yolu: {env_path.absolute()}")
    print("Lütfen .env dosyasının 'python 3d' klasörü içinde olduğundan emin olun.")
    exit(1) # Uygulamayı durdur

def check_monai_ready():
    """Check if MONAI Label service is ready."""
    try:
        res = requests.get(f"{MONAI_URL}/health", timeout=5)
        return res.status_code == 200
    except Exception:
        return False

# URL Encoding for MongoDB Password
encoded_pass = urllib.parse.quote_plus(MONGO_PASS)
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{encoded_pass}@{MONGO_CLUSTER}/?appName=Cluster0"

try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["doktor_paneli"] 
    hastalar_col = db["patients"]
    mongo_client.admin.command('ping')
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

# --- 1. PATIENT UPLOAD ---
@app.post("/upload-patient")
async def upload_patient(files: List[UploadFile] = File(...), name: str = Form(...)):
    patient_uuid = None
    upload_count = 0
    try:
        for file in files:
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

        if not patient_uuid: raise Exception("Orthanc upload failed.")

        hastalar_col.update_one(
            {"orthanc_id": patient_uuid},
            {
                "$set": {
                    "name": name, 
                    "orthanc_id": patient_uuid, 
                    "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                "$setOnInsert": {"createdAt": time.strftime("%Y-%m-%d %H:%M:%S")}
            },
            upsert=True
        )
        return {"status": "success", "uuid": patient_uuid, "files_uploaded": upload_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- 2. GET PATIENTS ---
@app.get("/patients")
async def get_patients():
    try:
        docs = list(hastalar_col.find().sort("createdAt", -1))
        # orthanc_id yoksa _id değerini string olarak gönder
        return [{"uuid": d.get("orthanc_id") or str(d.get("_id")), "display": d.get("name") or "İsimsiz"} for d in docs]
    except Exception as e:
        print(f"Error fetching patients: {e}")
        return []

# --- DELETE PATIENT ---
@app.delete("/patient/{patient_uuid}")
async def delete_patient(patient_uuid: str):
    from bson import ObjectId
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

# --- 3. AI SEGMENTATION ---
@app.get("/segment/{patient_uuid}")
async def run_segmentation(patient_uuid: str):
    fd, temp_nii = tempfile.mkstemp(suffix=".nii.gz")
    os.close(fd)
    try:
        p_info = requests.get(f"{ORTHANC_URL}/patients/{patient_uuid}", auth=('orthanc', 'orthanc')).json()
        series_id = requests.get(f"{ORTHANC_URL}/studies/{p_info['Studies'][0]}", auth=('orthanc', 'orthanc')).json()['Series'][0]
        dicom_uid = requests.get(f"{ORTHANC_URL}/series/{series_id}", auth=('orthanc', 'orthanc')).json()['MainDicomTags']['SeriesInstanceUID']

        payload = {"params": {"device": "cuda:0", "sw_batch_size": 1, "roi_size": [128, 128, 128], "overlap": 0.50}}
        res = requests.post(f"{MONAI_URL}/infer/segmentation?image={dicom_uid}", json=payload, timeout=None)
        
        if res.status_code != 200: raise Exception("AI Service Error")

        content = res.content
        gzip_start = content.find(b'\x1f\x8b\x08')
        with open(temp_nii, "wb") as f: f.write(content[gzip_start:])

        nifti = nib.load(temp_nii)
        data = nifti.get_fdata()
        zooms = nifti.header.get_zooms()
        all_meshes = []
        
        for label, (name, color) in ORGAN_MAP.items():
            mask = (data == label).astype(np.uint8)
            if not np.any(mask): continue
            
            grid = pv.ImageData(dimensions=mask.shape, spacing=zooms)
            grid.point_data["values"] = mask.flatten(order="F")
            mesh = grid.contour([0.5]).decimate(0.95).smooth_taubin(n_iter=20) 
            
            if mesh.n_points > 0:
                all_meshes.append({
                    "name": name, "color": color,
                    "vertices": mesh.points.tolist(),
                    "faces": mesh.faces.reshape((-1, 4))[:, 1:4].tolist()
                })
        return {"meshes": all_meshes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_nii): os.remove(temp_nii)

@app.post("/reset-vram")
async def reset_vram():
    try:
        subprocess.run(["docker", "restart", "monai_label_server"], check=True)
        # Sadece 3 saniye bekleyip başarı döndürüyoruz, uzun süre beklemek 500 hatasına neden oluyor.
        time.sleep(3)
        return {"status": "ready", "message": "VRAM sıfırlama tetiklendi"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)