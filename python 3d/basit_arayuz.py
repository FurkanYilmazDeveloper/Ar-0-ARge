import streamlit as st
import requests
import pyvista as pv
import nibabel as nib
import numpy as np
import plotly.graph_objects as go
import os
import time
import subprocess

# --- KONFİGÜRASYON ---
ORTHANC_URL = "http://127.0.0.1:8042" # Localhost üzerinden erişim
MONAI_URL = "http://127.0.0.1:8000"

ORGAN_MAP = {
    1: ('Spleen (Dalak)', '#3b82f6'),
    2: ('Right Kidney (Sağ Böbrek)', '#10b981'),
    3: ('Left Kidney (Sol Böbrek)', '#059669'),
    5: ('Liver (Karaciğer)', '#ef4444'),
    6: ('Stomach (Mide)', '#f97316'),
    10: ('Pancreas (Pankreas)', '#facc15'),
}

st.set_page_config(page_title="VRAM Dostu Organ Analizi", layout="wide")

def safe_get(path):
    try:
        r = requests.get(f"{ORTHANC_URL}/{path}", auth=('orthanc', 'orthanc'), timeout=5)
        return r.json() if r.status_code == 200 else None
    except: return None


# --- VRAM SIFIRLAMA VE RESTART MANTIĞI ---
if st.sidebar.button("♻️ VRAM Sıfırla & Sistemi Tazele", use_container_width=True):
    with st.spinner("MONAI Label Yeniden Başlatılıyor... VRAM Boşaltılıyor."):
        try:
            # Docker container'ı restart et (Container isminin monai_label_server olduğundan emin ol)
            subprocess.run(["docker", "restart", "monai_label_server"], check=True)
            
            # Servisin ayağa kalkmasını bekle (Health Check)
            max_retries = 30
            retry_count = 0
            ready = False
            
            while retry_count < max_retries:
                try:
                    # /info endpoint'ine istek atarak servis geldi mi kontrol et
                    check_res = requests.get(f"{MONAI_URL}/info", timeout=2)
                    if check_res.status_code == 200:
                        ready = True
                        break
                except:
                    pass
                
                retry_count += 1
                time.sleep(1) # her saniye kontrol et
            
            if ready:
                st.sidebar.success("✅ Sistem Hazır! VRAM Temizlendi.")
                time.sleep(1)
                st.rerun()
            else:
                st.sidebar.error("❌ Sistem başlatılamadı. Docker'ı kontrol et.")
                
        except Exception as e:
            st.sidebar.error(f"Docker Restart Hatası: {e}")
            st.sidebar.info("Not: Streamlit'in Docker komutlarını çalıştırma izni olduğundan emin olun.")

# --- SIDEBAR: HASTA YÖNETİMİ ---
st.sidebar.header("📋 Hasta Listesi")
patient_uuids = safe_get("patients")

if patient_uuids:
    # Uzun ID'ler yerine PatientID etiketlerini eşleştiriyoruz
    patient_display_list = {}
    for uuid in patient_uuids:
        p_data = safe_get(f"patients/{uuid}")
        if p_data:
            # DICOM içindeki kısa PatientID'yi alıyoruz, yoksa UUID'nin ilk 8 karakterini kullanıyoruz
            p_id_label = p_data.get('MainDicomTags', {}).get('PatientID', uuid[:8])
            patient_display_list[p_id_label] = uuid
    
    selected_label = st.sidebar.selectbox("Hasta Seçin (PatientID)", list(patient_display_list.keys()))
    selected_pid = patient_display_list[selected_label]
    
    p_info = safe_get(f"patients/{selected_pid}")
    
    if p_info and 'Studies' in p_info:
        series_id = safe_get(f"studies/{p_info['Studies'][0]}")['Series'][0]
        dicom_uid = safe_get(f"series/{series_id}")['MainDicomTags']['SeriesInstanceUID']
        
        st.title(f"🔍 Karın Bölgesi Analizi: {selected_label}")
        
        if st.button("🚀 3D SEGMENTASYONU BAŞLAT (VRAM OPTİMİZE)"):
            # PROGRESS BAR BAŞLANGICI
            progress_text = "AI Analizi Yapılıyor. Lütfen bekleyin..."
            my_bar = st.progress(0, text=progress_text)
            
            # KRİTİK: VRAM AYARLARINI KORUDUK
            payload = {
                "params": {
                    "device": "cuda:0",
                    "sw_batch_size": 1,        
                    "roi_size": [128, 128, 128],  
                    "overlap": 0.50,
                    "result_dtype": "uint8"
                }
            }
            
            try:
                # Progress barı %30'a getiriyoruz (Bağlantı kuruluyor)
                my_bar.progress(30, text="GPU Modeli Hazırlanıyor...")
                
                url = f"{MONAI_URL}/infer/segmentation?image={dicom_uid}"
                res = requests.post(url, json=payload, timeout=600)
                
                # Progress barı %80'e getiriyoruz (Veri işlendi, indiriliyor)
                my_bar.progress(80, text="Veri Paketi Çözülüyor...")
                
                if res.status_code == 200:
                    boundary = res.headers.get('Content-Type').split('boundary=')[-1].encode()
                    parts = res.content.split(boundary)
                    for part in parts:
                        if b'\x1f\x8b\x08' in part:
                            file_start = part.find(b'\x1f\x8b\x08')
                            st.session_state['mask_data'] = part[file_start:].rstrip(b'--\r\n')
                            st.session_state['ready'] = True
                            
                            # Başarı durumunda barı %100 yapıyoruz
                            my_bar.progress(100, text="Analiz Tamamlandı!")
                            time.sleep(1) # Barın dolduğunu görmek için kısa bir bekleme
                            st.rerun()
                else:
                    st.error(f"Sunucu Hatası: {res.status_code}")
                    my_bar.empty()
            except Exception as e:
                st.error(f"Hata: {e}")
                my_bar.empty()

# --- 3D GÖRSELLEŞTİRME ---
if st.session_state.get('ready'):
    with open("temp_mask.nii.gz", "wb") as f:
        f.write(st.session_state['mask_data'])
    
    nifti = nib.load("temp_mask.nii.gz")
    data = nifti.get_fdata()
    
    fig = go.Figure()
    
    unique_labels = np.unique(data)
    for label in unique_labels:
        if label == 0 or label not in ORGAN_MAP: continue
        
        name, color = ORGAN_MAP[label]
        mask = (data == label).astype(np.uint8)
        
        grid = pv.ImageData()
        grid.dimensions = mask.shape
        grid.spacing = nifti.header.get_zooms()
        grid.point_data["values"] = mask.flatten(order="F")
        
        mesh = grid.contour([0.5])
        if mesh.n_points > 0:
            mesh = mesh.decimate(0.95).smooth_taubin(n_iter=30)
            
            vertices = mesh.points
            faces = mesh.faces.reshape((-1, 4))[:, 1:4]
            
            fig.add_trace(go.Mesh3d(
                x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
                i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
                color=color, opacity=0.7, name=name, showlegend=True
            ))

    fig.update_layout(
        scene=dict(xaxis_visible=False, yaxis_visible=False, zaxis_visible=False),
        margin=dict(l=0, r=0, b=0, t=0),
        height=700,
        paper_bgcolor="#0e1117",
        legend=dict(font=dict(color="white"), yanchor="top", y=0.99, xanchor="left", x=0.01)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    st.caption("💡 Sağdaki listeden organ isimlerine tıklayarak gizleyebilir veya gösterebilirsin.")