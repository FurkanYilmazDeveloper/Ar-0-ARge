import os, time, requests, nibabel as nib, pyvista as pv, numpy as np, tempfile, shutil
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- KONFİGÜRASYON ---
ORTHANC_URL = "http://127.0.0.1:8042"
MONAI_URL = "http://127.0.0.1:8000"

# MongoDB Atlas Bağlantısı (db_password kısmını kendi şifrenle değiştir!)
MONGO_URI = "mongodb+srv://furkanyilmazandev_db_user:<db_password>@cluster0.fn4srdj.mongodb.net/?appName=Cluster0"

try:
    mongo_client = MongoClient(MONGO_URI)
    # Atlas üzerindeki isimlerle eşliyoruz:
    db = mongo_client["doktor_paneli"] 
    hastalar_col = db["patients"]
    # Bağlantı testi
    mongo_client.admin.command('ping')
    print("✅ MongoDB Atlas Bulut Bağlantısı Başarılı!")
except Exception as e:
    print(f"❌ MongoDB Bağlantı Hatası: {e}")

ORGAN_MAP = {1: ('Spleen', '#3b82f6'), 2: ('R-Kidney', '#10b981'), 3: ('L-Kidney', '#059669'), 
             5: ('Liver', '#ef4444'), 6: ('Stomach', '#f97316'), 10: ('Pancreas', '#facc15')}

# --- 1. YENİ HASTA YÜKLEME (Atlas'a Kaydeder) ---
@app.post("/upload-patient")
async def upload_patient(file: UploadFile = File(...), name: str = Form(...)):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    try:
        # A. Orthanc'a Gönder
        with open(temp_path, "rb") as f:
            orthanc_res = requests.post(f"{ORTHANC_URL}/instances", data=f.read(), auth=('orthanc', 'orthanc')).json()
        patient_uuid = orthanc_res['ParentPatient']

        # B. MongoDB Atlas'a Kaydet (Arkadaşınla ortak havuz)
        hastalar_col.insert_one({
            "name": name, 
            "orthanc_id": patient_uuid, 
            "createdAt": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        return {"status": "success", "uuid": patient_uuid}
    except Exception as e: return {"status": "error", "message": str(e)}
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

# --- 2. HASTA LİSTESİNİ GETİR (Atlas'tan Çeker) ---
@app.get("/patients")
async def get_patients():
    try:
        # 1. Direkt MongoDB Atlas'tan tüm hastaları çek
        # (Orthanc'ta olup olmamasına bakmaksızın listeler)
        docs = list(hastalar_col.find().sort("createdAt", -1))
        
        results = []
        for doc in docs:
            results.append({
                "uuid": doc.get("orthanc_id", "yok"), # Orthanc'ta yoksa 'yok' döner
                "display": doc.get("name") or doc.get("isim") or "İsimsiz Hasta"
            })
        
        print(f"--- Atlas'tan {len(results)} hasta getirildi.")
        return results
    except Exception as e:
        print(f"Liste çekme hatası: {e}")
        return []

# --- 3. AI ANALİZ VE MESH OLUŞTURMA ---
@app.get("/segment/{patient_uuid}")
async def run_segmentation(patient_uuid: str):
    fd, temp_nii = tempfile.mkstemp(suffix=".nii.gz")
    os.close(fd)
    try:
        p_info = requests.get(f"{ORTHANC_URL}/patients/{patient_uuid}", auth=('orthanc', 'orthanc')).json()
        series_id = requests.get(f"{ORTHANC_URL}/studies/{p_info['Studies'][0]}", auth=('orthanc', 'orthanc')).json()['Series'][0]
        dicom_uid = requests.get(f"{ORTHANC_URL}/series/{series_id}", auth=('orthanc', 'orthanc')).json()['MainDicomTags']['SeriesInstanceUID']

        # ROI size VRAM dostu tutuldu
        payload = {"params": {"device": "cuda:0", "sw_batch_size": 1, "roi_size": [64, 64, 64], "overlap": 0.0}}
        res = requests.post(f"{MONAI_URL}/infer/segmentation?image={dicom_uid}", json=payload, timeout=None)
        
        content = res.content
        gzip_start = content.find(b'\x1f\x8b\x08')
        if gzip_start == -1: raise Exception("Gecersiz AI Yaniti")
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
            # Yüksek basitleştirme ile akıcı performans
            mesh = grid.contour([0.5]).decimate(0.95) 
            if mesh.n_points > 0:
                all_meshes.append({
                    "name": name, "color": color,
                    "vertices": mesh.points.tolist(),
                    "faces": mesh.faces.reshape((-1, 4))[:, 1:4].tolist()
                })
        return {"meshes": all_meshes}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_nii): os.remove(temp_nii)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)