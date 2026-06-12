/** Preset structured submissions for demoing without real document images. */

export const SAMPLES: Record<string, { label: string; payload: unknown }> = {
  clean: {
    label: "Clean consultation (full approval)",
    payload: {
      member_id: "EMP001",
      policy_id: "PLUM_GHI_2024",
      claim_category: "CONSULTATION",
      treatment_date: "2024-11-01",
      claimed_amount: 1500,
      ytd_claims_amount: 5000,
      documents: [
        {
          file_id: "F007",
          actual_type: "PRESCRIPTION",
          content: {
            doctor_name: "Dr. Arun Sharma",
            doctor_registration: "KA/45678/2015",
            patient_name: "Rajesh Kumar",
            date: "2024-11-01",
            diagnosis: "Viral Fever",
            medicines: ["Paracetamol 650mg", "Vitamin C 500mg"],
          },
        },
        {
          file_id: "F008",
          actual_type: "HOSPITAL_BILL",
          content: {
            hospital_name: "City Clinic, Bengaluru",
            patient_name: "Rajesh Kumar",
            date: "2024-11-01",
            line_items: [
              { description: "Consultation Fee", amount: 1000 },
              { description: "CBC Test", amount: 300 },
              { description: "Dengue NS1 Test", amount: 200 },
            ],
            total: 1500,
          },
        },
      ],
    },
  },
  wrongDoc: {
    label: "Wrong document (stops early)",
    payload: {
      member_id: "EMP001",
      policy_id: "PLUM_GHI_2024",
      claim_category: "CONSULTATION",
      treatment_date: "2024-11-01",
      claimed_amount: 1500,
      documents: [
        { file_id: "F001", file_name: "dr_sharma_prescription.jpg", actual_type: "PRESCRIPTION" },
        { file_id: "F002", file_name: "another_prescription.jpg", actual_type: "PRESCRIPTION" },
      ],
    },
  },
  dental: {
    label: "Dental with cosmetic item (partial)",
    payload: {
      member_id: "EMP002",
      policy_id: "PLUM_GHI_2024",
      claim_category: "DENTAL",
      treatment_date: "2024-10-15",
      claimed_amount: 12000,
      documents: [
        {
          file_id: "F011",
          actual_type: "HOSPITAL_BILL",
          content: {
            hospital_name: "Smile Dental Clinic",
            patient_name: "Priya Singh",
            line_items: [
              { description: "Root Canal Treatment", amount: 8000 },
              { description: "Teeth Whitening", amount: 4000 },
            ],
            total: 12000,
          },
        },
      ],
    },
  },
  degraded: {
    label: "Component failure (graceful degradation)",
    payload: {
      member_id: "EMP006",
      policy_id: "PLUM_GHI_2024",
      claim_category: "ALTERNATIVE_MEDICINE",
      treatment_date: "2024-10-28",
      claimed_amount: 4000,
      simulate_component_failure: true,
      documents: [
        {
          file_id: "F021",
          actual_type: "PRESCRIPTION",
          content: {
            doctor_name: "Vaidya T. Krishnan",
            doctor_registration: "AYUR/KL/2345/2019",
            diagnosis: "Chronic Joint Pain",
            treatment: "Panchakarma Therapy",
          },
        },
        {
          file_id: "F022",
          actual_type: "HOSPITAL_BILL",
          content: {
            hospital_name: "Ayur Wellness Centre",
            total: 4000,
            line_items: [
              { description: "Panchakarma Therapy (5 sessions)", amount: 3000 },
              { description: "Consultation", amount: 1000 },
            ],
          },
        },
      ],
    },
  },
};
