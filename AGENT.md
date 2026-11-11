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

- **`app/config.py`**: penambahan konfigurasi MinIO (`MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET/SECURE`), Qwen/OpenAI-compatible LLM (`QWEN_API_KEY/BASE_URL/MODEL`), fallback model (`LLM_FALLBACK_MODELS`) + timeout/retry (`LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`), batas upload (`MAX_UPLOAD_SIZE_MB`), dan kontrol biaya token (`LLM_CLAIM_EXTRACTION`, `LLM_EVALUATION`, `LLM_CLAIM_TEXT_MAX_CHARS`, `LLM_MAX_EVIDENCE_PER_CLAIM`, `LLM_EVIDENCE_EXCERPT_MAX_CHARS`), dengan `extra="ignore"`.
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

## 7. Integrasi 9router & Fallback LLM

- **`app/services/llm_client.py`** *(baru)*: client OpenAI-compatible terpusat. `chat_json()` mencoba `QWEN_MODEL` lebih dulu, lalu `LLM_FALLBACK_MODELS` secara berurutan bila terjadi error, kuota habis, atau output bukan JSON valid; mengembalikan `(data, model_used)` atau `None`. Selalu mengirim `stream=false` (beberapa provider 9router mengembalikan SSE bila field ini kosong), memakai `LLM_TIMEOUT_SECONDS`/`LLM_MAX_RETRIES`, dan mencatat model fallback yang dipakai ke log.
- **`app/agents/claim_extraction.py` & `app/agents/analysis.py`**: tidak lagi membuat client OpenAI sendiri; keduanya memakai `chat_json()` sehingga otomatis mendapat fallback model, lalu tetap jatuh ke heuristik bila semua model gagal.
- **`.env.example`**: contoh konfigurasi 9router (`QWEN_BASE_URL=http://YOUR_9ROUTER_HOST:20128/v1`, `QWEN_MODEL=alims-intl/qwen-flash`) beserta rantai fallback gratis dan variabel kontrol token.

## 8. Queue PostgreSQL, Dedupe PDF, dan Share Hasil

- **`app/models/analysis_jobs.py`** *(baru)*: entitas `analysis_jobs` (`analysis_id` unik, `document_id`, `user_id`, `file_hash`, status `queued|running|completed|failed`, `attempts`, `last_error`, `run_after`, `locked_until`, timestamp). Index unik parsial `(user_id, file_hash) WHERE status IN ('queued','running')` mencegah dua job aktif untuk PDF yang sama.
- **`app/models/analyses.py` & `app/models/documents.py`**: tambah `share_token`/`shared_at` pada analyses dan `file_hash` pada documents.
- **`app/services/analysis_queue.py`** *(baru)*: worker thread PostgreSQL-backed tanpa Redis. Klaim job dengan `SELECT ... FOR UPDATE SKIP LOCKED`, proses pipeline memakai session sendiri, tandai completed/failed, dan pulihkan job `running` yang tertinggal saat startup (bersihkan claims/evidence parsial lalu requeue).
- **`app/services/file_hash.py`** *(baru)*: SHA-256 isi PDF untuk dedupe.
- **`app/services/analyze_pipeline.py`**: tetap dipakai worker tanpa perubahan alur; ekstraksi dokumen, klaim, evidence, evaluasi, QC, dan visualisasi berjalan di background.
- **`app/routes/analyze.py`**: `POST /analyze` memvalidasi, menghitung hash, mengecek job aktif/hasil completed milik user yang sama, menyimpan PDF ke MinIO, membuat `Analyses`+`Documents`+`AnalysisJob` dalam satu transaksi, lalu `wake_worker()` dan mengembalikan `202`. Endpoint baru: `GET /analyses/{id}/status`, `POST/DELETE /analyses/{id}/share`, dan `GET /public/analyses/{token}` (tanpa auth). `GET /analyses/{id}` mengembalikan `202` + status selama belum selesai dan hasil lengkap hanya saat `completed`.
- **`app/main.py`**: lifespan menjalankan `start_worker()` setelah `create_all` dan `stop_worker()` saat shutdown.
- **`app/config.py`**: `ANALYSIS_QUEUE_ENABLED`, `ANALYSIS_WORKER_POLL_SECONDS`, `ANALYSIS_JOB_MAX_ATTEMPTS`, `SHARE_BASE_URL`.
- **`migrations_queue_dedupe_share.sql`** *(baru)* + **`db_satusurvey.sql`**: kolom/tabel/index/constraint untuk queue, hash, share, dan status `queued` (idempotent untuk DB existing).
- **`tests/test_queue_and_hash.py`** *(baru)*: stabilitas SHA-256 dan pembentukan share URL.
- **`app/routes/llm_proxy.py`** *(baru)*: passthrough OpenAI-compatible terautentikasi ke 9router privat. Hanya path `models`, `chat/completions`, `completions`, dan `embeddings` yang diteruskan; API key disuntik di server, header client yang sensitif dibuang, dan respons di-stream. Digerbangi `LLM_PROXY_ENABLED` serta `get_current_user` sehingga tidak menjadi relay publik.
- **Frontend** (ringkas): `lib/api.ts` + `lib/hooks.ts` polling status, halaman `/share/[token]` publik, panel share/copy link, badge status `queued`, dan notifikasi hasil dedupe.

## 9. Catatan Operasional

- Jalankan `migrations_analyze.sql` pada DB existing bila diperlukan; pastikan MinIO & (opsional) Tesseract/Poppler untuk OCR tersedia. Konfigurasi LLM dan batas token melalui `.env`. Restart server setelah perubahan. Verifikasi kompilasi: `python -m compileall app tests`; pengujian: `PYTHONPATH=. pytest -q` (bila `pytest` terpasang).
