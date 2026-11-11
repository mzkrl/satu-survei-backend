# AGENT.md — Implemented Changes (SatuSurvey Backend)

Dokumen ini merangkum perubahan yang diimplementasikan pada codebase selama sesi pengembangan/pemeliharaan ini.

## 1. Model & Schema Domain (sesuai skema SQL MVP)

- **`app/models/users.py`**: diselaraskan (`email` opsional, kolom password konsisten dengan pemakaian aplikasi).
- **`app/models/analyses.py`** *(baru)*: entitas `Analyses` (`id`, `user_id`, `title`, `status` default `draft`, `created_at`), relasi ke `documents` dan `claims` (cascade delete-orphan). `__tablename__` diset ke `analyses`.
- **`app/models/documents.py`** *(baru)*: entitas `Documents` (FK `analysis_id` → `analyses.id` ON DELETE CASCADE, metadata file/publikasi, `status` default `pending`, `extracted_text`), relasi ke `analysis`, `evidence`, `claims`.
- **`app/models/evidence.py`** *(baru)*: entitas `Evidence` (FK `document_id`, `metric`, `value` Numeric(20,6), `unit/population/geography/period`, `sample_size`, `raw_excerpt`, `page_number`, `metadata` JSONB default `{}` dipetakan `metadata_` dengan properti `metadata`, `created_at`).
- **`app/models/claims.py`** *(baru/diperbarui)*: entitas `Claims` (FK `analysis_id` dan `document_id`, `statement`, `category`, `status` default `pending`, `raw_excerpt`, `page_number` untuk provenance), relasi ke `analysis`, `document`, `evaluations`.
- **`app/models/evaluations.py`** *(baru)*: entitas `Evaluations` (FK `claim_id`, `verdict`, `confidence` Numeric(5,4), `explanation`, `evidence_ids`/`limitations` JSONB array, `metrics` JSONB), relasi ke `claim`; riwayat evaluasi dipertahankan (append).
- **`app/models/__init__.py`**: ekspor `Users`, `Analyses`, `Documents`, `Evidence`, `Claims`, `Evaluations`.
- **Schema Pydantic** (`app/schemas/`): `analyses.py`, `documents.py`, `evidence.py`, `claims.py`, `evaluations.py` *(baru)* masing-masing `Base/Create/Update/Response` (UUID, `datetime/date/Decimal`, validasi seperti `sample_size >= 0`, `page_number > 0`, `confidence` 0–1, `from_attributes`); `claims` menyertakan `document_id`/`raw_excerpt`/`page_number`; `evaluations` mendukung verdict `valid|questionable|invalid|insufficient_evidence`. `app/schemas/analyze.py` *(baru)* untuk respons `/analyze`. `app/schemas/__init__.py` diperbarui untuk mengekspor schema baru.

## 2. Skema Database & Migrasi

- **`db_satusurvey.sql`**: diperbarui agar selaras dengan model (termasuk `claims.document_id`, `raw_excerpt`, `page_number` dan CHECK verdict evaluasi mencakup `insufficient_evidence`).
- **`migrations_analyze.sql`** *(baru)*: migrasi SQL idempotent untuk DB existing (`ALTER TABLE claims` tambah kolom/provenance & index, penyesuaian constraint verdict evaluasi). `Base.metadata.create_all()` tidak mengubah tabel lama, sehingga migrasi/ALTER diperlukan untuk skema yang sudah ada.

## 3. Konfigurasi & Aplikasi

- **`app/config.py`**: penambahan konfigurasi MinIO (`MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET/SECURE`), Qwen/OpenAI-compatible LLM (`QWEN_API_KEY/BASE_URL/MODEL`), batas upload (`MAX_UPLOAD_SIZE_MB`), dan kontrol biaya token (`LLM_CLAIM_EXTRACTION`, `LLM_EVALUATION`, `LLM_CLAIM_TEXT_MAX_CHARS`, `LLM_MAX_EVIDENCE_PER_CLAIM`, `LLM_EVIDENCE_EXCERPT_MAX_CHARS`), dengan `extra="ignore"`.
- **`app/main.py`**: registrasi router `analyze`, serta `lifespan` startup yang menjalankan `Base.metadata.create_all(bind=engine)` (dengan import model) untuk membuat tabel yang belum ada.
- **`.env.example`** & **`requirements.txt`**: diperbarui (variabel MinIO/Qwen/upload; dependensi seperti `minio`, `openai`, `pypdf`, `pdf2image`, `pillow`, `pytesseract`, dll.).

## 4. Endpoint `POST /analyze` & Pipeline (modular)

- **`app/routes/analyze.py`** *(baru)*: endpoint `POST /analyze` (auth). Validasi upload PDF (ekstensi/content-type, signature `%PDF`, non-kosong, batas ukuran → 400/413), penyimpanan file ke MinIO via object key (bukan biner di DB), pembuatan record `Analysis`/`Document`, orkestrasi pipeline, penanganan status/error (422/500) dan pengembalian hasil terstruktur.
- **`app/services/file_storage.py`** *(baru)*: integrasi MinIO (ensure bucket, upload PDF, penyimpanan path/key).
- **`app/services/document_extraction.py`** *(baru/diperbaiki)*: ekstraksi teks PDF native (`pypdf`) per halaman, fallback OCR per halaman teks-rendah (`pdf2image`/`pytesseract` bila tersedia), metadata (judul/publisher/tanggal), output terstruktur; **perbaikan** `_parse_pdf_date` agar menangani `datetime/date` dari metadata pypdf (bukan hanya string).
- **`app/services/evidence_extraction.py`** *(baru)*: ekstraksi & normalisasi evidence deterministik dari teks bertanda halaman (nilai numerik, normalisasi pemisah desimal mis. `52,75`/`1.234,56`, `unit/period`, `raw_excerpt`, `page_number`, provenance).
- **`app/services/analyze_pipeline.py`** *(baru)*: orkestrasi bertahap — ekstraksi dokumen, ekstraksi klaim, **ekstraksi/persistensi evidence (Stage 3b)**, evaluasi per klaim (append riwayat), quality control, dan penyiapan visualisasi; pengelolaan status `processing/completed/failed`, logging jumlah (evidence/claims/evaluations), dan persistensi hasil.
- **`app/services/visualization.py`** *(baru)*: transformasi hasil tervalidasi ke data frontend (ringkasan, distribusi verdict, detail klaim+evidence/metrics/limitations, perbandingan/time-series dari data yang tersedia, laporan QC) tanpa fabrikasi nilai.
- **`app/agents/claim_extraction.py`** *(baru)*: ekstraksi klaim faktual (LLM Qwen OpenAI-compatible bila dikonfigurasi, fallback heuristik), deduplikasi, validasi Pydantic, preservasi `raw_excerpt`/`page_number`; batas teks input LLM dapat dikonfigurasi.
- **`app/agents/analysis.py`** *(baru/diperbaiki)*: evaluasi klaim terhadap evidence terpilih (pencocokan numerik/konteks/periode dengan normalisasi desimal & scoring), seleksi evidence relevan per klaim, payload LLM diringkas, **heuristik-first** (LLM evaluasi hanya saat perlu & dapat dimatikan) untuk hemat token; verdict `valid|questionable|invalid|insufficient_evidence` tanpa fabrikasi evidence.
- **`app/agents/quality_control.py`** *(baru/diperbaiki)*: validasi provenance klaim/evidence/evaluasi, referensi & konsistensi, koreksi deterministik aman; cek kelengkapan semantik (`no_evidence_extracted`, `all_claims_unmatched` + penandaan re-evaluasi, provenance evidence hilang) agar kondisi kosong/tak tertaut tidak lolos sebagai `passed`.
- **`app/services/__init__.py`, `app/agents/__init__.py`** *(baru)*: inisialisasi paket.

## 5. Perbaikan Bug/Konsistensi

- Penanganan metadata tanggal PDF bertipe `datetime` pada ekstraksi dokumen (`document_extraction`).
- Penyesuaian nama tabel model Analyses ke `analyses` agar sesuai FK/relasi.
- Inisialisasi tabel otomatis saat startup (`create_all`) untuk lingkungan yang belum memiliki tabel pipeline.
- Optimalisasi penggunaan token LLM (seleksi evidence relevan, pembatasan/pemangkasan konteks, jalur heuristik-first, flag on/off per tahap).

## 6. Pengujian

- **`tests/test_document_extraction.py`**: validasi signature PDF dan ambang kebutuhan OCR.
- **`tests/test_claim_extraction.py`**: perilaku ekstraksi klaim & field provenance.
- **`tests/test_quality_control.py`**: deteksi isu (excerpt hilang, referensi evidence buruk) dan koreksi deterministik.
- **`tests/test_visualization.py`**: konsistensi ringkasan/distribusi/output visualisasi.
- **`tests/test_evidence_pipeline.py`** *(baru)*: normalisasi pemisah desimal, ekstraksi & pencocokan evidence untuk klaim numerik dan perbandingan historis.

## 7. Catatan Operasional

- Jalankan `migrations_analyze.sql` pada DB existing bila diperlukan; pastikan MinIO & (opsional) Tesseract/Poppler untuk OCR tersedia. Konfigurasi LLM dan batas token melalui `.env`. Restart server setelah perubahan. Verifikasi kompilasi: `python -m compileall app tests`; pengujian: `PYTHONPATH=. pytest -q` (bila `pytest` terpasang).
