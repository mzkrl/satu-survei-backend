# Satu Survey

Backend API untuk analisis klaim dan evidence. Lihat `AGENT.md` untuk status pengembangan dan fitur yang sudah tersedia.

## Prasyarat

- Python 3.11 atau lebih baru
- PostgreSQL 14 atau lebih baru
- Docker dan Docker Compose
- Git
- Opsional untuk OCR PDF hasil scan: Tesseract OCR dan Poppler

### Linux (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip postgresql postgresql-contrib tesseract-ocr poppler-utils git
```

Docker:

```bash
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

Nama paket Docker berbeda antar distro. Jika `docker-compose-v2` tidak tersedia, instal Docker Engine dan plugin Compose dari dokumentasi resmi Docker.

### macOS

```bash
brew install python@3.12 postgresql@16 tesseract poppler git
brew install --cask docker
brew services start postgresql@16
export PATH="$(brew --prefix postgresql@16)/bin:$PATH"
```

Buka Docker Desktop satu kali agar daemon berjalan:

```bash
open -a Docker
```

Tambahkan baris `export PATH=...` ke `~/.zshrc` agar `psql` tersedia di shell baru.

### Windows

Instal melalui installer:

- Python 3.11+ dari https://www.python.org/downloads/. Centang `Add python.exe to PATH`.
- PostgreSQL dari https://www.postgresql.org/download/windows/.
- Docker Desktop dari https://www.docker.com/products/docker-desktop/.
- Tesseract OCR dari https://github.com/UB-Mannheim/tesseract/wiki.
- Poppler dari https://github.com/oschwartz10612/poppler-windows/releases. Tambahkan folder `bin` Tesseract dan Poppler ke `PATH`.
- Git for Windows dari https://git-scm.com/download/win.

Buka PowerShell baru, lalu cek:

```powershell
python --version
psql --version
docker --version
docker compose version
```

## 1. Siapkan Konfigurasi

Dari direktori `backend`:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit `.env` dan sesuaikan:

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` dengan kredensial PostgreSQL.
- `SECRET_KEY` dengan nilai acak. Generate dengan:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

- `MINIO_ACCESS_KEY` dan `MINIO_SECRET_KEY`. Nilai ini juga dipakai oleh `docker-compose.yml`, jadi harus sama.
- `QWEN_API_KEY`, `QWEN_BASE_URL`, dan `QWEN_MODEL` bila memakai LLM. Bagian ini boleh dikosongkan; pipeline memiliki fallback heuristik.
- `MAX_UPLOAD_SIZE_MB` sesuai batas ukuran PDF yang diinginkan.

Jangan commit file `.env`.

## 2. Siapkan PostgreSQL

Jalankan service PostgreSQL:

Linux:

```bash
sudo systemctl enable --now postgresql
```

macOS:

```bash
brew services start postgresql@16
```

Windows:

```powershell
Get-Service postgresql*
Start-Service postgresql-x64-16
```

Sesuaikan nama service dengan versi PostgreSQL yang terpasang.

Buat database dan muat skema.

Linux, menggunakan role `postgres`:

```bash
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'ganti-password-kuat';"
sudo -u postgres psql -c "CREATE DATABASE db_satusurvey;"
sudo -u postgres psql -d db_satusurvey -f db_satusurvey.sql
```

Samakan `DB_USER` dan `DB_PASSWORD` di `.env` dengan role tersebut.

macOS, buat role khusus agar kredensial `.env` konsisten:

```bash
psql -d postgres -c "CREATE ROLE satusurvey LOGIN SUPERUSER PASSWORD 'ganti-password-kuat';"
createdb -O satusurvey db_satusurvey
psql -U satusurvey -d db_satusurvey -f db_satusurvey.sql
```

Set `DB_USER=satusurvey` dan `DB_PASSWORD` yang sama di `.env`.

Role dibuat `SUPERUSER` karena `db_satusurvey.sql` menjalankan `CREATE EXTENSION pgcrypto`. Untuk lingkungan produksi, cabut hak superuser setelah skema selesai diimpor.

Windows, menggunakan role `postgres` dan password yang diisi saat instalasi:

```powershell
psql -U postgres -c "CREATE DATABASE db_satusurvey;"
psql -U postgres -d db_satusurvey -f db_satusurvey.sql
```

Jika `psql` tidak ditemukan di Windows, gunakan path lengkap:

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE db_satusurvey;"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d db_satusurvey -f db_satusurvey.sql
```

`db_satusurvey.sql` tidak idempotent. Jalankan sekali pada database baru. Saat aplikasi start, `create_all` hanya membuat tabel yang belum ada; skrip SQL tetap diperlukan untuk extension, constraint, dan index.

## 3. Siapkan MinIO

Dari direktori `backend`:

```bash
docker compose up -d
docker compose ps
```

- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`
- Login memakai `MINIO_ACCESS_KEY` dan `MINIO_SECRET_KEY` dari `.env`.
- Bucket `MINIO_BUCKET` dibuat otomatis saat upload pertama.

Data disimpan di `./storage/minio`. Hentikan container dengan:

```bash
docker compose down
```

## 4. Instal Dependensi Python

Pilih salah satu: `pip` atau `uv`.

### Opsi A: pip

Linux dan macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jika aktivasi diblokir kebijakan PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Windows CMD:

```bat
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

### Opsi B: uv

Instal uv.

Linux dan macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Atau melalui Homebrew:

```bash
brew install uv
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Buka terminal baru, lalu buat environment dan instal dependensi.

Linux dan macOS:

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Windows PowerShell:

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

Tanpa aktivasi venv:

```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn app.main:app --reload
```

Opsional, tentukan versi Python saat membuat venv:

```bash
uv venv --python 3.12
```

## 5. Jalankan Server

Dengan venv aktif:

```bash
uvicorn app.main:app --reload
```

Buka:

- API: `http://127.0.0.1:8000`
- Dokumentasi: `http://127.0.0.1:8000/docs`

Dengan uv:

```bash
uv run uvicorn app.main:app --reload
```

Verifikasi server:

```bash
curl http://127.0.0.1:8000/
```

Di Windows PowerShell, gunakan `curl.exe` agar tidak memakai alias `Invoke-WebRequest`:

```powershell
curl.exe http://127.0.0.1:8000/
```

Respons yang diharapkan:

```json
{"message":"Hello World! API is Running. Proceed to /docs"}
```

### Akses dari Perangkat Lain

Default `uvicorn` hanya listen di `127.0.0.1`. Untuk menerima koneksi dari jaringan lokal:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Dengan uv:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Akses dari perangkat lain memakai IP host, misalnya `http://192.168.1.10:8000/docs`.

Catatan:

- `0.0.0.0` membuka server ke semua interface jaringan. Batasi dengan firewall bila perlu. Di Windows, izinkan port `8000` pada Windows Firewall saat diminta.
- Jangan ekspos server langsung ke internet. Gunakan reverse proxy, TLS, dan autentikasi.
- `docker-compose.yml` memetakan MinIO ke semua interface. Untuk akses lokal saja, ubah port menjadi `127.0.0.1:9000:9000` dan `127.0.0.1:9001:9001`.
