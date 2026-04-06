const mongoose = require("mongoose");

const patientSchema = new mongoose.Schema(
  {
    name: { type: String, required: true, trim: true },
    age: { type: Number, required: true, min: 0, max: 150 },
    gender: { type: String, trim: true, default: "" },
    mrType: { type: String, trim: true, default: "MR" },
    finding: { type: String, trim: true, default: "" },
    recentDaysAgo: { type: Number, default: 0, min: 0 },
    mrImage: { type: String, default: "" },
    accent: { type: String, default: "#0078d4" },
  },
  { timestamps: true }
);

module.exports = mongoose.model("Patient", patientSchema);
