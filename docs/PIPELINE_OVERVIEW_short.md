# VSL26 Pipeline Overview Short

```mermaid
flowchart TD
    A["Raw Vietnamese Prescription Image<br/>JPG/PNG"] --> B["Stage 1: OCR<br/>EasyOCR + VietOCR"]
    B -->|"words + bounding boxes"| C["Stage 2: NER<br/>LayoutLMv3 on VAIPE-P<br/>F1 0.9911 + sliding window"]
    C --> D["Stage 2.5: Spatial Association<br/>drug ↔ quantity ↔ usage"]
    D --> E["Stage 3: Medicine Mapper<br/>SQLite KB: 4760+ drugs<br/>9500+ aliases"]
    E --> F["Stage 4: Gloss Generation<br/>4-section drug template<br/>+ universal closing"]
    F --> G["Stage 5: VSL Footage Index<br/>token → clip ID"]
    G --> H["Stage 6: Video Assembly<br/>concatenate clips"]
    H --> I["Final VSL Video"]
    I --> J["Stage 7: User Evaluation<br/>deaf children comprehension study"]

    classDef done fill:#d8f5dd,stroke:#2f8f46,color:#0f3d1c,stroke-width:2px;
    classDef progress fill:#fff3bf,stroke:#d6a800,color:#4a3800,stroke-width:2px;
    classDef blocked fill:#ffd6d6,stroke:#c92a2a,color:#5a0b0b,stroke-width:2px;
    class A,B,C,D,E,F,G done;
    class H progress;
    class J blocked;
```

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
└── docs/PIPELINE_OVERVIEW.md # full overview
```

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
