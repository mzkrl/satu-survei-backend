# SatuSurvey — Aturan Main untuk AI Coding Agent

Baca `plan.md` dulu. File ini adalah salinan bagian 10 plan.

1. **Baca `plan.md` dulu.** Kerjakan **satu milestone per sesi**, jangan loncat. Centang checkbox saat selesai.
2. **Test dulu** untuk logika murni (`rules/`, `grounding`, `qc`, `metadata`). Jalankan `pytest` sebelum menyatakan selesai.
3. **Jangan pernah memanggil API LLM asli di test.** Gunakan `FakeLLMClient`.
4. **Jangan menambah dependency** di luar daftar M0 tanpa bertanya.
5. **Tidak ada logika bisnis di view.** View hanya memanggil service.
6. **Output LLM = usulan, bukan fakta.** Semuanya lewat QC; skor/rule dihitung kode, bukan LLM.
7. **Jangan `|safe`**, jangan `mark_safe` pada konten dokumen/LLM.
8. **Jangan log isi dokumen.** Log hanya id, tahap, percobaan, kode error.
9. **Jangan hardcode** nama model, API key, atau path. Semua dari env.
10. **Gunakan bahasa netral** di UI; jangan menulis kata "bohong", "manipulatif", "palsu" terhadap survei.
11. Type hints di semua fungsi publik; fungsi kecil dan bernama jelas; satu commit per milestone dengan pesan `Mx: …`.
12. Bila spesifikasi ambigu: pilih opsi paling sederhana yang konsisten dengan bagian 2, lalu catat asumsi di akhir `plan.md` bagian 14.

## Perintah

```
.venv\Scripts\python.exe -m pytest        # test
.venv\Scripts\python.exe manage.py runserver
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py seed_demo          # muat demo dari cache (tanpa LLM)
# produksi (Linux): gunicorn config.wsgi --timeout 180
```

Virtualenv: `.venv` (Python 3.12, via uv). Django 5.2.x.
