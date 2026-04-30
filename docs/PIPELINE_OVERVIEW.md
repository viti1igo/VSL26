# VSL26 Pipeline Overview

VSL26 converts Vietnamese prescription images into structured Vietnamese Sign Language (VSL) gloss and video assets for a pilot comprehension study with deaf children.

## Section 1: High-Level Pipeline Diagram

```mermaid
flowchart TD
    A["Raw Vietnamese Prescription Image<br/>JPG/PNG"] --> B["Stage 1: OCR<br/>EasyOCR detection + VietOCR recognition"]
    B -->|"words + bounding boxes"| C["Stage 2: NER<br/>LayoutLMv3 fine-tuned on VAIPE-P<br/>F1 0.9911<br/>+ sliding window inference"]
    C -->|"6 entity types"| D["Stage 2.5: Spatial Association<br/>Bounding box proximity matching<br/>drug ↔ quantity ↔ usage"]
    D -->|"structured drugs list"| E["Stage 3: Medicine Mapper<br/>SQLite KB: 4760+ drugs<br/>Fuzzy matching + brand aliases"]
    E -->|"drug + clinical purpose"| F["Stage 4: Gloss Generation<br/>4-section template per drug<br/>+ universal closing"]
    F -->|"gloss token sequences"| G["Stage 5: VSL Footage Index<br/>Token → clip ID lookup"]
    G -->|"clip ID list"| H["Stage 6: Video Assembly<br/>Concatenate raw VSL clips"]
    H --> I["Final VSL Video<br/>For deaf children"]
    I --> J["Stage 7: User Evaluation<br/>Comprehension study<br/>with deaf children"]

    classDef done fill:#d8f5dd,stroke:#2f8f46,color:#0f3d1c,stroke-width:2px;
    classDef progress fill:#fff3bf,stroke:#d6a800,color:#4a3800,stroke-width:2px;
    classDef blocked fill:#ffd6d6,stroke:#c92a2a,color:#5a0b0b,stroke-width:2px;
    class A,B,C,D,E,F,G done;
    class H progress;
    class J blocked;
```

## Section 2: Data Flow Diagram

Example prescription: `VAIPE_P_TRAIN_679`, which contains `KAVASDIN 5 5mg` for hypertension.

```mermaid
flowchart TD
    A["Raw image<br/>VAIPE_P_TRAIN_679.png<br/>Vietnamese prescription scan"] --> B["OCR output<br/>[{text: 'KAVASDIN 55 mg',<br/>box: [x1,y1,x2,y2],<br/>confidence: 0.9+}, ...]"]
    B --> C["NER output<br/>date / diagnose / usage / quantity / drugname / other<br/>drugname: 'KAVASDIN 55 mg'<br/>diagnose: 'Bệnh lý tăng huyết áp'"]
    C --> D["Spatial association output<br/>drugs: [{name: 'KAVASDIN 55 mg',<br/>quantity: linked same-row quantity,<br/>usage: linked same-row usage}]"]
    D --> E["Mapper output<br/>PrescriptionMapping JSON<br/>name_extracted: 'KAVASDIN 55 mg'<br/>name_normalized: 'Amlodipin'<br/>match_confidence: 100"]
    E --> F["Gloss output<br/>dung_cho: ['bác sĩ kê thuốc','số 1','giảm','nguy cơ','cao huyết áp']<br/>dung_nhu_nao: ['uống','buổi sáng','mỗi ngày']<br/>luu_y: ['uống','đều đặn','mỗi ngày','không','tự ý','ngừng thuốc']<br/>universal_closing: allergy + emergency actions"]
    F --> G["Footage IDs<br/>['VSL_DOCTOR_PRESCRIBE', 'VSL_008_so1',<br/>'VSL_004_giam', 'VSL_027_cao_huyet_ap', ...]"]
    G --> H["Video output<br/>Concatenated MP4 from ordered VSL clips"]
```

## Section 3: Knowledge Base Architecture

```mermaid
flowchart LR
    A["WHO ATC Database<br/>4755 drugs imported"] --> D["vaipe_drugs.db<br/>SQLite knowledge base"]
    B["Project-specific drugs<br/>from VAIPE-P frequency analysis"] --> C["Human review + LLM curation<br/>Wave 1: 32 verified drugs added"]
    C --> D
    E["Brand name aliases<br/>9500+ entries"] --> D
    F["Traditional Vietnamese medicines<br/>7 entries with custom flag"] --> D
```

## Section 4: Pilot Study Setup

| Prescription ID | Target drug detected | Canonical drug | Diagnosis context | What it tests |
|---|---|---|---|---|
| `VAIPE_P_TRAIN_679` | `KAVASDIN 5 5mg` | Amlodipine | Hypertension | Brand-name antihypertensive → generic → hypertension gloss |
| `VAIPE_P_TRAIN_456` | `ENALAPRIL 5mg` | Enalapril | Primary hypertension | Generic antihypertensive with hypertension warning template |
| `VAIPE_P_TRAIN_871` | `AMOXICILIN 500MG 500mg` | Amoxicillin | Injury / infection-adjacent prescription context | Antibiotic gloss and mandatory complete-course warning |
| `VAIPE_P_TRAIN_877` | `PANACTOL 500mg` | Paracetamol | Headache | Pain relief gloss and paracetamol dose-safety warning |

## Section 5: File Structure

```text
VSL26/
├── inference.py              # Stage 2: NER with sliding window
├── ocr_engine.py             # Stage 1: OCR
├── medicine_mapper.py        # Stages 3-4: Mapper + Gloss
├── test_full_pipeline.py     # End-to-end pipeline test
├── test_gloss_engine.py      # Pilot prescription gloss test
├── models/                   # LayoutLMv3 fine-tuned checkpoint
├── public_train/             # VAIPE-P dataset (1173 prescriptions)
├── vaipe_drugs.db            # Knowledge base
├── results/                  # All outputs
└── docs/PIPELINE_OVERVIEW.md # this document
```

## Section 6: Key Research Findings

- LayoutLMv3 `max_length=224` truncation dropped drug rows in long prescriptions; this was solved with sliding-window inference.
- Vietnamese prescriptions use brand names most of the time, not generics, so brand-alias mapping is essential.
- The pipeline abstracts `brand → generic → clinical purpose` so deaf children receive meaning-focused VSL instead of raw drug names.
- Traditional Vietnamese medicines require special handling because many do not have a single Western generic or ATC code.
- The KB was built from WHO ATC plus VAIPE-P frequency-driven curation and Wave 1 human-verified additions.
- Pilot study scope is intentionally narrow: 4 drugs, 4 pilot prescriptions, and fully specified gloss templates.

## Section 7: Current Status & Next Steps

- ✅ OCR pipeline (EasyOCR + VietOCR)
- ✅ NER model (LayoutLMv3 F1 0.9911)
- ✅ Sliding window inference for long documents
- ✅ Bounding box spatial association
- ✅ Drug knowledge base (4760+ drugs)
- ✅ Structured gloss generation (4 sections per drug)
- 🔧 Drug-usage spatial pairing fine-tuning
- ⏸️ VSL footage ID assignment for new gloss tokens
- ⏸️ Video assembly script
- ⏸️ Pilot user evaluation with deaf children
- ⏸️ Ethics approval submission
