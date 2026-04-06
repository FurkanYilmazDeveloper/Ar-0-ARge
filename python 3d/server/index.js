require("dotenv").config();
const path = require("path");
const express = require("express");
const cors = require("cors");
const mongoose = require("mongoose");
const Patient = require("./models/Patient");

const PORT = Number(process.env.PORT) || 3000;
const MONGODB_URI = process.env.MONGODB_URI;

if (!MONGODB_URI) {
  console.error("MONGODB_URI tanımlı değil. server/.env dosyasına ekleyin (bkz. .env.example).");
  process.exit(1);
}

const app = express();
app.use(cors());
app.use(express.json({ limit: "2mb" }));

const rootDir = path.join(__dirname, "..");
app.use(express.static(rootDir));

app.get("/api/health", (_req, res) => {
  const ready = mongoose.connection.readyState === 1;
  res.json({ ok: true, mongo: ready ? "connected" : "disconnected" });
});

app.get("/api/patients", async (_req, res) => {
  try {
    const docs = await Patient.find().sort({ createdAt: -1 }).lean();
    res.json(docs);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Hastalar alınamadı" });
  }
});

app.post("/api/patients", async (req, res) => {
  try {
    const b = req.body || {};
    const payload = {
      name: String(b.name ?? "").trim(),
      age: Number(b.age),
      gender: String(b.gender ?? "").trim(),
      mrType: String(b.mrType ?? "").trim() || "MR",
      finding: String(b.finding ?? "").trim(),
      recentDaysAgo: b.recentDaysAgo === "" || b.recentDaysAgo == null ? 0 : Number(b.recentDaysAgo),
      mrImage: String(b.mrImage ?? "").trim(),
      accent: String(b.accent ?? "").trim() || "#0078d4",
    };
    const doc = await Patient.create(payload);
    res.status(201).json(doc);
  } catch (err) {
    console.error(err);
    res.status(400).json({ error: err.message || "Kayıt oluşturulamadı" });
  }
});

async function main() {
  await mongoose.connect(MONGODB_URI, {
    serverSelectionTimeoutMS: 8000,
  });
  app.listen(PORT, () => {
    console.log(`Sunucu: http://localhost:${PORT}`);
    console.log(`API: http://localhost:${PORT}/api/patients`);
  });
}

main().catch((err) => {
  console.error("MongoDB bağlantı hatası:", err.message);
  process.exit(1);
});
