import slicer
from slicer.ScriptedLoadableModule import *
import qt, requests, os

class ArArgeOrganAnaliz(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "ArArge Organ Analiz"
        self.parent.categories = ["Custom AI Tools"]
        self.parent.contributors = ["ArArge"]

class ArArgeOrganAnalizWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        # UI Temizleme (Reload sırasında çakışmayı önler)
        if self.parent.layout() is not None:
            for i in reversed(range(self.parent.layout().count())): 
                item = self.parent.layout().itemAt(i)
                if item.widget(): item.widget().setParent(None)
            self.layout = self.parent.layout()
        else:
            self.layout = qt.QVBoxLayout(self.parent)

        # --- HASTA YÖNETİMİ ---
        self.patientGroup = qt.QGroupBox("📂 Hasta Yönetimi")
        pLayout = qt.QVBoxLayout(self.patientGroup)
        self.layout.addWidget(self.patientGroup)

        self.patientList = qt.QListWidget()
        self.patientList.setFixedHeight(150)
        pLayout.addWidget(self.patientList)

        self.refreshBtn = qt.QPushButton("🔄 Listeyi Güncelle")
        self.refreshBtn.clicked.connect(self.onRefreshPatients)
        pLayout.addWidget(self.refreshBtn)

        manageBtnLayout = qt.QHBoxLayout()
        pLayout.addLayout(manageBtnLayout)

        self.addBtn = qt.QPushButton("➕ Yeni Hasta Ekle")
        self.addBtn.clicked.connect(self.onAddPatient)
        manageBtnLayout.addWidget(self.addBtn)

        self.deleteBtn = qt.QPushButton("🗑️ Hastayı Sil")
        self.deleteBtn.setStyleSheet("color: #991b1b;")
        self.deleteBtn.clicked.connect(self.onDeletePatient)
        manageBtnLayout.addWidget(self.deleteBtn)

        # --- ANALİZ ---
        self.analysisBtn = qt.QPushButton("🚀 AI ANALİZİNİ BAŞLAT")
        self.analysisBtn.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; height: 55px; border-radius: 12px;")
        self.analysisBtn.clicked.connect(self.onRunAnalysis)
        self.layout.addWidget(self.analysisBtn)

        # --- 3D GÖRÜNÜM KONTROLÜ ---
        self.toggle3DBtn = qt.QPushButton("🌐 3D Modeli Oluştur / Göster")
        self.toggle3DBtn.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: white; 
                font-weight: bold; height: 40px; border-radius: 8px;
                margin-top: 5px;
            }
            QPushButton:hover { background-color: #047857; }
        """)
        self.toggle3DBtn.clicked.connect(self.onToggle3D)
        self.layout.addWidget(self.toggle3DBtn)

        # --- ORGAN GÖRÜNÜRLÜĞÜ ---
        organGroup = qt.QGroupBox("👁️ Organ Görünürlüğü")
        self.organLayout = qt.QVBoxLayout(organGroup)
        self.layout.addWidget(organGroup)
        
        self.organs = [
    "spleen",
    "kidney_right",
    "kidney_left",
    "gallbladder",
    "liver",
    "stomach",
    "aorta",
    "inferior_vena_cava",
    "portal_vein_and_splenic_vein",
    "pancreas",
    "adrenal_gland_right",
    "adrenal_gland_left",
    "lung_upper_lobe_left",
    "lung_lower_lobe_left",
    "lung_upper_lobe_right",
    "lung_middle_lobe_right",
    "lung_lower_lobe_right",
    "esophagus",
    "trachea",
    "heart_myocardium",
    "heart_atrium_left",
    "heart_ventricle_left",
    "heart_atrium_right",
    "heart_ventricle_right",
    "pulmonary_artery"
]
        for organ in self.organs:
            cb = qt.QCheckBox(organ.replace('_', ' ').capitalize())
            cb.checked = True
            cb.stateChanged.connect(lambda state, o=organ: self.onToggleOrgan(o, state))
            self.organLayout.addWidget(cb)

        self.layout.addStretch(1)

    # --- FONKSİYONLAR ---

    def onRefreshPatients(self):
        self.patientList.clear()
        try:
            r = requests.get("http://127.0.0.1:8001/patients", timeout=3)
            for p in r.json():
                item = qt.QListWidgetItem(f"👤 {p['display']}")
                item.setData(qt.Qt.UserRole, p['uuid'])
                self.patientList.addItem(item)
            slicer.util.showStatusMessage("Liste güncellendi.", 2000)
        except:
            slicer.util.errorDisplay("FastAPI bağlantı hatası!")

    def onAddPatient(self):
        result = qt.QInputDialog.getText(None, "Yeni Hasta", "Hasta Adı Soyadı:")
        name = result[0] if isinstance(result, tuple) else result
        ok = result[1] if isinstance(result, tuple) else (result != "")
        if ok and name:
            path = qt.QFileDialog.getExistingDirectory(None, "DICOM Klasörünü Seç")
            if path:
                try:
                    slicer.util.showStatusMessage(f"{name} yükleniyor...", 5000)
                    files = []
                    for f in os.listdir(path):
                        if f.lower().endswith(('.dcm', '.dicom')):
                            files.append(('files', (f, open(os.path.join(path, f), 'rb'), 'application/dicom')))
                    r = requests.post("http://127.0.0.1:8001/upload-patient", data={'name': name}, files=files, timeout=60)
                    if r.status_code == 200:
                        slicer.util.delayDisplay("Başarıyla eklendi.")
                        self.onRefreshPatients()
                    else: slicer.util.errorDisplay(f"Hata: {r.text}")
                except Exception as e: slicer.util.errorDisplay(str(e))

    def onDeletePatient(self):
        selected = self.patientList.currentItem()
        if not selected: return
        uuid = selected.data(qt.Qt.UserRole)
        if qt.QMessageBox.question(None, "Onay", "Silinsin mi?", qt.QMessageBox.Yes | qt.QMessageBox.No) == qt.QMessageBox.Yes:
            try:
                requests.delete(f"http://127.0.0.1:8001/patient/{uuid}", timeout=5)
                self.onRefreshPatients()
            except: slicer.util.errorDisplay("Silme başarısız!")

    def onRunAnalysis(self):
        selectedItem = self.patientList.currentItem()
        if not selectedItem:
            slicer.util.errorDisplay("Önce listeden bir hasta seçmelisin!")
            return
        
        patient_uuid = selectedItem.data(qt.Qt.UserRole)

        try:
            # 1. MONAI Label Modülüne geç
            slicer.util.selectModule('MONAILabel')
            mw = slicer.modules.monailabel.widgetRepresentation()
            
            # 2. ADRES KUTUSUNU DÜZELT (Az önceki hatayı tamir eder)
            serverBox = mw.findChild('QComboBox', 'serverComboBox')
            if serverBox:
                serverBox.setEditText("http://127.0.0.1:8000")
                # Sunucu bilgilerini tazele (Hata mesajını siler)
                refreshServerBtn = mw.findChild('QPushButton', 'fetchServerInfoButton')
                if refreshServerBtn:
                    refreshServerBtn.click()
            
            slicer.app.processEvents() # Slicer'ın kendine gelmesini bekle

            # 3. GÖRÜNTÜYÜ ÇEK (Doğru kutuyu bularak)
            # Senin listende 'inputSelector' muhtemelen görüntü kutusu
            inputBox = mw.findChild('QComboBox', 'inputSelector')
            if inputBox:
                inputBox.setEditText(patient_uuid)
            
            # 'Next Sample' butonuna bas (Görüntüyü indirir)
            fetchBtn = mw.findChild('QPushButton', 'nextSampleButton')
            if fetchBtn:
                slicer.util.showStatusMessage(f"Görüntü getiriliyor: {patient_uuid}", 3000)
                fetchBtn.click()
            
            slicer.app.processEvents()

            # 4. ANALİZİ (RUN) BAŞLAT
            # Senin listendeki gerçek ismi: 'segmentationButton'
            runButton = mw.findChild('QPushButton', 'segmentationButton')
            
            if runButton:
                # Görüntünün inmesi için 3 saniye bekle ve tıkla
                qt.QTimer.singleShot(3000, lambda: self.safeRun(runButton))
                slicer.util.showStatusMessage("Analiz birazdan başlayacak...", 5000)
                
                # Kendi modülüne dön
                qt.QTimer.singleShot(4000, lambda: slicer.util.selectModule('ArArgeOrganAnaliz'))
            else:
                slicer.util.errorDisplay("Hata: 'Run' butonu (segmentationButton) bulunamadı!")

        except Exception as e:
            slicer.util.errorDisplay(f"Sistem Hatası: {str(e)}")

    def safeRun(self, button):
        """Buton aktifse tıklar"""
        if button.enabled:
            button.click()
        else:
            slicer.util.showStatusMessage("Görüntü yükleniyor, lütfen 'Run' butonuna elinizle basın.", 5000)

    def onToggleOrgan(self, organName, state):
        nodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        if not nodes: return
        node = nodes[-1]
        displayNode = node.GetDisplayNode()
        segmentation = node.GetSegmentation()
        
        # --- FİLTRELEME BAŞLIYOR: Listede olmayanları gizle ---
        for i in range(segmentation.GetNumberOfSegments()):
            current_id = segmentation.GetNthSegmentID(i)
            current_name = segmentation.GetSegment(current_id).GetName().lower()
            
            # Eğer bu organ senin self.organs listende (spleen, liver vb.) YOKSA, gizle!
            if not any(o in current_name for o in self.organs):
                displayNode.SetSegmentVisibility(current_id, False)
        # --- FİLTRELEME BİTTİ ---

        # Tıkladığın organı aç/kapat (Mevcut mantığın devamı)
        sid = ""
        for i in range(segmentation.GetNumberOfSegments()):
            cid = segmentation.GetNthSegmentID(i)
            if organName.lower() in segmentation.GetSegment(cid).GetName().lower():
                sid = cid
                break
        
        if sid and displayNode:
            displayNode.SetSegmentVisibility(sid, state == qt.Qt.Checked)

    def onToggle3D(self):
        # 1. Segmentasyon düğmesini bul
        nodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        if not nodes:
            slicer.util.errorDisplay("Hata: Ekranda henüz bir analiz sonucu yok!")
            return
        
        node = nodes[-1]
        
        # 2. 3D Mesh Hesaplamasını Zorla (En önemli kısım)
        slicer.util.showStatusMessage("3D Modeller hesaplanıyor... Bu işlem birkaç saniye sürebilir.", 5000)
        # Slicer'a 'Hadi artık şu 2D boyamaları 3D yap' diyoruz
        node.CreateClosedSurfaceRepresentation() 
        
        # 3. Görünürlüğü Aktif Et
        displayNode = node.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility3D(True)
            # Tüm organların 3D görünürlüğünü tek tek kontrol et (garantiye alalım)
            segmentation = node.GetSegmentation()
            for i in range(segmentation.GetNumberOfSegments()):
                segmentId = segmentation.GetNthSegmentID(i)
                displayNode.SetSegmentVisibility3D(segmentId, True)

        # 4. KAMERAYI ODAKLA (Modeli göremiyor olabilirsin, bu komut modeli merkeze alır)
        layoutManager = slicer.app.layoutManager()
        threeDWidget = layoutManager.threeDWidget(0)
        threeDView = threeDWidget.threeDView()
        threeDView.resetFocalPoint() # Kamerayı objeye zıplatır
        
        slicer.util.showStatusMessage("3D Model başarıyla oluşturuldu ve odaklandı!", 3000)        