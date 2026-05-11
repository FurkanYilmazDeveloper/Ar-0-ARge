import slicer
from slicer.ScriptedLoadableModule import *
import qt, requests, os, json, vtk

class ArArgeOrganAnaliz(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "ArArge Organ Analiz"
        self.parent.categories = ["Custom AI Tools"]
        self.parent.contributors = ["ArArge"]

class ArArgeOrganAnalizWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        # Token ve Kullanıcı Bilgileri
        self.authToken = None
        self.userRole = None
        self.api_url = "http://127.0.0.1:8001"

        if self.parent.layout() is not None:
            for i in reversed(range(self.parent.layout().count())): 
                item = self.parent.layout().itemAt(i)
                if item.widget(): item.widget().setParent(None)
            self.layout = self.parent.layout()
        else:
            self.layout = qt.QVBoxLayout(self.parent)

        # --- GİRİŞ PANELİ (HER ZAMAN GÖRÜNÜR) ---
        self.loginGroup = qt.QGroupBox("🔐 Sisteme Giriş")
        lLayout = qt.QFormLayout(self.loginGroup)
        self.layout.addWidget(self.loginGroup)

        self.usernameEntry = qt.QLineEdit()
        self.usernameEntry.placeholderText = "Kullanıcı Adı"
        lLayout.addRow("Kullanıcı:", self.usernameEntry)

        self.passwordEntry = qt.QLineEdit()
        self.passwordEntry.setEchoMode(qt.QLineEdit.Password)
        self.passwordEntry.placeholderText = "Şifre"
        lLayout.addRow("Şifre:", self.passwordEntry)

        self.loginBtn = qt.QPushButton("Giriş Yap")
        self.loginBtn.setStyleSheet("background-color: #4b5563; color: white; font-weight: bold; height: 30px;")
        self.loginBtn.clicked.connect(self.onLogin)
        lLayout.addRow(self.loginBtn)

        self.logoutBtn = qt.QPushButton("Oturumu Kapat")
        self.logoutBtn.setStyleSheet("background-color: #991b1b; color: white; font-weight: bold; height: 30px;")
        self.logoutBtn.visible = False
        self.logoutBtn.clicked.connect(self.onLogout)
        lLayout.addRow(self.logoutBtn)

        self.statusLabel = qt.QLabel("Durum: Giriş Bekleniyor...")
        self.statusLabel.setStyleSheet("color: #6b7280; font-size: 10px;")
        lLayout.addRow(self.statusLabel)

        # --- GİZLENEBİLİR ALANLAR (BAŞLANGIÇTA GİZLİ) ---
        
        # Hasta Listesi Grubu
        self.patientGroup = qt.QGroupBox("📂 Hasta Listesi")
        self.patientGroup.visible = False # <--- GİZLENDİ
        pLayout = qt.QVBoxLayout(self.patientGroup)
        self.layout.addWidget(self.patientGroup)

        self.patientList = qt.QListWidget()
        self.patientList.setFixedHeight(180)
        pLayout.addWidget(self.patientList)

        self.refreshBtn = qt.QPushButton("🔄 Listeyi Yenile")
        self.refreshBtn.clicked.connect(self.onRefreshPatients)
        pLayout.addWidget(self.refreshBtn)

        # Analiz Butonu
        self.analysisBtn = qt.QPushButton("🚀 AI ANALİZİNİ BAŞLAT")
        self.analysisBtn.visible = False # <--- GİZLENDİ
        self.analysisBtn.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; height: 50px; border-radius: 10px; margin-top: 10px;")
        self.analysisBtn.clicked.connect(self.onRunAnalysis)
        self.layout.addWidget(self.analysisBtn)

        # 3D Modeli Butonu
        self.toggle3DBtn = qt.QPushButton("🌐 3D Modeli Oluştur")
        self.toggle3DBtn.visible = False # <--- GİZLENDİ
        self.toggle3DBtn.setStyleSheet("background-color: #059669; color: white; font-weight: bold; height: 35px; border-radius: 5px;")
        self.toggle3DBtn.clicked.connect(self.onToggle3D)
        self.layout.addWidget(self.toggle3DBtn)

        # Organ Visibility Group
        self.organVisibilityGroup = qt.QGroupBox("👁️ Organ Görünürlüğü (Aç/Kapat)")
        self.organVisibilityGroup.visible = False
        self.organVisibilityLayout = qt.QVBoxLayout(self.organVisibilityGroup)
        
        self.scrollArea = qt.QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setFixedHeight(150)
        self.scrollWidget = qt.QWidget()
        self.scrollLayout = qt.QGridLayout(self.scrollWidget)
        self.scrollArea.setWidget(self.scrollWidget)
        self.organVisibilityLayout.addWidget(self.scrollArea)
        
        self.layout.addWidget(self.organVisibilityGroup)

        self.layout.addStretch(1)

    def onLogin(self):
        username = self.usernameEntry.text
        password = self.passwordEntry.text

        try:
            r = requests.post(f"{self.api_url}/login", 
                             json={"username": username, "password": password}, 
                             timeout=5)
            
            if r.status_code == 200:
                data = r.json()
                self.authToken = data['access_token']
                self.userRole = data['role']
                
                self.statusLabel.text = f"Durum: Giriş Başarılı ({self.userRole})"
                self.statusLabel.setStyleSheet("color: #16a34a; font-weight: bold;")
                
                # --- UI GÜNCELLEME (GİZLİLERİ GÖSTER) ---
                self.loginBtn.visible = False
                self.logoutBtn.visible = True
                self.usernameEntry.enabled = False
                self.passwordEntry.enabled = False
                
                self.patientGroup.visible = True
                self.analysisBtn.visible = True
                self.toggle3DBtn.visible = True
                
                self.onRefreshPatients()
            else:
                slicer.util.errorDisplay("Hatalı kullanıcı adı veya şifre!")
        except Exception as e:
            slicer.util.errorDisplay(f"Sunucuya bağlanılamadı: {str(e)}")

    def onLogout(self):
        """Oturumu sonlandırır ve arayüzü tekrar gizler"""
        self.authToken = None
        self.userRole = None
        
        # --- UI GÜNCELLEME (GİZLE) ---
        self.patientList.clear()
        self.usernameEntry.enabled = True
        self.passwordEntry.enabled = True
        self.passwordEntry.text = ""
        self.loginBtn.visible = True
        self.logoutBtn.visible = False
        
        self.patientGroup.visible = False
        self.analysisBtn.visible = False
        self.toggle3DBtn.visible = False
        self.organVisibilityGroup.visible = False
        
        self.statusLabel.text = "Durum: Oturum Kapatıldı"
        self.statusLabel.setStyleSheet("color: #6b7280; font-size: 10px;")
        slicer.util.showStatusMessage("Çıkış yapıldı.", 2000)

    def onRefreshPatients(self):
        if not self.authToken: return
        self.patientList.clear()
        headers = {"Authorization": f"Bearer {self.authToken}"}
        try:
            r = requests.get(f"{self.api_url}/patients", headers=headers, timeout=5)
            if r.status_code == 200:
                for p in r.json():
                    item = qt.QListWidgetItem(f"👤 {p['display']}")
                    item.setData(qt.Qt.UserRole, p['uuid'])
                    self.patientList.addItem(item)
        except Exception as e:
            slicer.util.errorDisplay(f"Liste güncellenemedi: {str(e)}")

    def onRunAnalysis(self):
        selectedItem = self.patientList.currentItem()
        if not selectedItem:
            slicer.util.errorDisplay("Lütfen bir hasta seçin!")
            return
        patient_uuid = selectedItem.data(qt.Qt.UserRole)
        try:
            slicer.util.selectModule('MONAILabel')
            mw = slicer.modules.monailabel.widgetRepresentation()
            serverBox = mw.findChild('QComboBox', 'serverComboBox')
            if serverBox: serverBox.setEditText("http://127.0.0.1:8000")
            inputBox = mw.findChild('QComboBox', 'inputSelector')
            if inputBox: inputBox.setEditText(patient_uuid)
            fetchBtn = mw.findChild('QPushButton', 'nextSampleButton')
            if fetchBtn: fetchBtn.click()
            qt.QTimer.singleShot(3000, lambda: self.triggerSegmentation(mw))
        except Exception as e:
            slicer.util.errorDisplay(f"Analiz başlatılamadı: {str(e)}")

    def triggerSegmentation(self, mw):
        runBtn = mw.findChild('QPushButton', 'segmentationButton')
        if runBtn and runBtn.enabled:
            runBtn.click()
            slicer.util.selectModule('ArArgeOrganAnaliz')

    def onToggle3D(self):
        nodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        if not nodes: return
        node = nodes[-1]
        node.CreateClosedSurfaceRepresentation() 
        displayNode = node.GetDisplayNode()
        if displayNode: displayNode.SetVisibility3D(True)
        layoutManager = slicer.app.layoutManager()
        layoutManager.threeDWidget(0).threeDView().resetFocalPoint()
        
        self.populateOrganButtons(node)

    def populateOrganButtons(self, segmentationNode):
        self.organVisibilityGroup.visible = True
        
        # Clear existing buttons
        for i in reversed(range(self.scrollLayout.count())): 
            item = self.scrollLayout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
                
        segmentation = segmentationNode.GetSegmentation()
        segmentIDs = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIDs)
        
        displayNode = segmentationNode.GetDisplayNode()
        
        row = 0
        col = 0
        for i in range(segmentIDs.GetNumberOfValues()):
            segmentID = segmentIDs.GetValue(i)
            segment = segmentation.GetSegment(segmentID)
            segmentName = segment.GetName()
            color = segment.GetColor()
            
            btn = qt.QPushButton(segmentName)
            btn.setCheckable(True)
            # Both 2D and 3D visibility can be set. Let's just toggle the segment's general visibility.
            btn.setChecked(displayNode.GetSegmentVisibility(segmentID))
            
            r, g, b = int(color[0]*255), int(color[1]*255), int(color[2]*255)
            
            self.updateBtnStyle(btn, btn.isChecked(), r, g, b)
            
            # Using default argument binding in lambda to avoid late binding issues
            btn.toggled.connect(lambda checked, sID=segmentID, button=btn, red=r, green=g, blue=b, dNode=displayNode: self.onOrganToggled(checked, sID, button, red, green, blue, dNode))
            
            self.scrollLayout.addWidget(btn, row, col)
            col += 1
            if col > 1: # 2 columns
                col = 0
                row += 1

    def updateBtnStyle(self, button, checked, r, g, b):
        if checked:
            button.setStyleSheet(f"background-color: rgb({r},{g},{b}); color: white; font-weight: bold; border-radius: 5px; padding: 5px; margin: 2px;")
        else:
            button.setStyleSheet(f"background-color: #374151; color: #9ca3af; border: 1px solid rgb({r},{g},{b}); border-radius: 5px; padding: 5px; margin: 2px;")

    def onOrganToggled(self, checked, segmentID, button, r, g, b, displayNode):
        displayNode.SetSegmentVisibility(segmentID, checked)
        self.updateBtnStyle(button, checked, r, g, b)