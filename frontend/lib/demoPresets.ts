/** Demo presets for the upload flow: form values + real document images
 * (served from /public/demo-documents) fetched and attached automatically. */

export interface DemoPreset {
  id: string;
  label: string;
  segment: string;
  memberId: string;
  category: string;
  treatmentDate: string;
  amount: number;
  hospital?: string;
  files: string[]; // file names under /demo-documents/
  expected: string;
}

export const DEMO_PRESETS: DemoPreset[] = [
  {
    id: "wrong-doc",
    label: "B — Wrong document type (stops early)",
    segment: "Demo segment 1",
    memberId: "EMP001",
    category: "CONSULTATION",
    treatmentDate: "2024-11-01",
    amount: 1500,
    files: [
      "A1_prescription_rajesh.jpg",
      "B1_prescription_rajesh_followup.jpg",
    ],
    expected:
      "Stops before any decision: names the uploaded type (2 prescriptions) " +
      "and the missing one (hospital bill).",
  },
  {
    id: "clean-approval",
    label: "A — Clean consultation (full approval)",
    segment: "Demo segment 2",
    memberId: "EMP001",
    category: "CONSULTATION",
    treatmentDate: "2024-11-01",
    amount: 1500,
    files: ["A1_prescription_rajesh.jpg", "A2_hospital_bill_rajesh.jpg"],
    expected:
      "APPROVED ₹1,350 (10% co-pay on ₹1,500), confidence ≈0.95, full " +
      "trace with source=vision extraction steps.",
  },
  {
    id: "network-discount",
    label: "F — Apollo network discount (TC010 math)",
    segment: "Demo segment 2 (alt)",
    memberId: "EMP010",
    category: "CONSULTATION",
    treatmentDate: "2024-11-03",
    amount: 4500,
    hospital: "Apollo Hospitals",
    files: ["F1_prescription_deepak.jpg", "F2_apollo_bill_deepak.jpg"],
    expected:
      "APPROVED ₹3,240 — 20% network discount first (₹4,500 → ₹3,600), " +
      "then 10% co-pay (→ ₹3,240). The ordering shows in the breakdown.",
  },
  {
    id: "blurry-bill",
    label: "C — Blurry pharmacy bill (re-upload ask)",
    segment: "Optional extra",
    memberId: "EMP004",
    category: "PHARMACY",
    treatmentDate: "2024-10-25",
    amount: 800,
    files: ["C1_prescription_sneha.jpg", "C2_pharmacy_bill_sneha_BLURRY.jpg"],
    expected:
      "Asks to re-upload just the blurry bill — does not reject the claim.",
  },
  {
    id: "patient-mismatch",
    label: "D — Documents from different patients",
    segment: "Optional extra",
    memberId: "EMP001",
    category: "CONSULTATION",
    treatmentDate: "2024-11-01",
    amount: 1500,
    files: ["A1_prescription_rajesh.jpg", "D1_hospital_bill_arjun_mehta.jpg"],
    expected:
      "Stops early naming both patients found: Rajesh Kumar (prescription) " +
      "vs Arjun Mehta (bill).",
  },
  {
    id: "dental-partial",
    label: "E — Dental with cosmetic item (partial)",
    segment: "Optional extra",
    memberId: "EMP002",
    category: "DENTAL",
    treatmentDate: "2024-10-15",
    amount: 12000,
    files: ["E1_dental_bill_priya.jpg"],
    expected:
      "PARTIAL ₹8,000 — root canal covered, teeth whitening excluded with a " +
      "per-line reason.",
  },
];

export async function fetchPresetFiles(preset: DemoPreset): Promise<File[]> {
  return Promise.all(
    preset.files.map(async (name) => {
      const res = await fetch(`/demo-documents/${name}`);
      if (!res.ok) throw new Error(`Could not load demo document ${name}`);
      const blob = await res.blob();
      return new File([blob], name, { type: "image/jpeg" });
    })
  );
}
