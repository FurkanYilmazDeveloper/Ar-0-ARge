# Doktor Paneli + MongoDB (Node.js)

Arayüz statik HTML/CSS/JS; hasta verileri MongoDB üzerinden Express + Mongoose API ile gelir.

## Gereksinimler

- Node.js 18+
- MongoDB (yerel veya Atlas)

## Kurulum

```powershell
cd server
npm install
```

`server\.env` içinde `MONGODB_URI` tanımlayın (şablon: `server\.env.example`).

## Çalıştırma

```powershell
cd server
npm start
```

Tarayıcı: [http://localhost:3000](http://localhost:3000)

API: `GET/POST http://localhost:3000/api/patients`

`mrImage` alanı boşsa arayüz hasta bilgisine göre basit bir SVG önizleme üretir; gerçek görsel için bu alana URL veya data URI yazın.
