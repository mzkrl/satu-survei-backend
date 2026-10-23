"""Generate PDF survei sintetis + manifest untuk demo.

Jalankan sekali: .venv\\Scripts\\python.exe scripts/generate_demo_pdfs.py
Menghasilkan demo/pdfs/*.pdf dan demo/pdfs/manifest.json (idempoten).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "demo" / "pdfs"

DOCS: list[dict] = [
    {
        "file": "kepuasan-pemerintah-2026.pdf",
        "title": "Survei Kepuasan Kinerja Pemerintah 2026",
        "publisher": "Lembaga Riset Contoh Nasional",
        "publication_date": "2026-04-10",
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "source_url": "",
        "notes": "Data sintetis untuk demonstrasi SatuSurvey. Disclosure lengkap, MoE konsisten.",
        "text": """
LAPORAN SURVEI KEPUASAN KINERJA PEMERINTAH 2026
Lembaga Riset Contoh Nasional

BAB 1 PENDAHULUAN
Laporan ini disusun oleh Lembaga Riset Contoh Nasional berdasarkan hasil
survei kepuasan kinerja pemerintah pusat periode Maret 2026. Survei ini
merupakan bagian dari seri riset berkala tentang tata kelola publik.

BAB 2 METODOLOGI
Survei ini menggunakan metode multistage random sampling. Sampel sebanyak
1.200 responden dipilih secara acak dari seluruh provinsi menggunakan
teknik penarikan berjenjang. Survei dilakukan secara tatap muka oleh
enumerator terlatih di rumah responden. Wawancara dilaksanakan pada
10 Maret 2026 hingga 25 Maret 2026. Populasi dalam survei ini adalah
seluruh WNI usia 17 tahun ke atas yang bertinggal di wilayah Nasional,
34 provinsi. Tingkat kepercayaan survei ini adalah 95 persen dengan
margin of error sebesar 2,9 persen. Pembobotan dilakukan berdasarkan
profil demografi populasi nasional (umur, jenis kelamin, dan wilayah).
Pendana riset ini berasal dari dana mandat internal lembaga. Redaksi
pertanyaan disusun oleh tim riset dan telah diuji coba pada 80 responden
pilot. Seluruh responden memberikan persetujuan tertulis sebelum
wawancara dimulai.

BAB 3 HASIL SURVEI
Temuan utama survei menunjukkan bahwa kepuasan kinerja pemerintah
sebesar 72,4 persen pada Maret 2026. Angka ini dihitung dari gabungan
kategori puas dan sangat puas. Kepercayaan publik terhadap lembaga
legislatif berada di angka 58,3 persen. Ketahanan pangan rumah tangga
juga menjadi sorotan, dengan 41,2 persen responden menyatakan kondisi
pangan keluarga cukup baik. Tingkat kepuasan terhadap layanan kesehatan
dasar tercatat 64,8 persen, sementara kepuasan terhadap layanan
pendidikan dasar 61,5 persen.

BAB 4 PENUTUP
Demikian laporan survei ini disampaikan. Data lengkap tersedia pada
lampiran yang merupakan bagian tidak terpisah dari laporan ini.
""",
    },
    {
        "file": "ekonomi-rumah-tangga-2026.pdf",
        "title": "Survei Kondisi Ekonomi Rumah Tangga 2026",
        "publisher": "Pusat Riset Kebijakan Publik Contoh",
        "publication_date": "2026-06-18",
        "period_start": "2026-05-01",
        "period_end": "2026-05-28",
        "source_url": "",
        "notes": "Data sintetis untuk demonstrasi SatuSurvey. Disclosure 7/9, MoE konsisten.",
        "text": """
LAPORAN SURVEI KONDISI EKONOMI RUMAH TANGGA 2026
Pusat Riset Kebijakan Publik Contoh

BAB 1 PENDAHULUAN
Laporan ini menyajikan hasil Survei Kondisi Ekonomi Rumah Tangga 2026
yang diselenggarakan oleh Pusat Riset Kebijakan Publik Contoh.
Survei bertujuan memantau daya beli dan ketahanan ekonomi rumah tangga.

BAB 2 METODOLOGI
Survei ini menggunakan metode stratified random sampling dengan
pembagian strata berdasarkan wilayah ekonomi. Sampel sebanyak 1.500
responden dipilih secara acak dari 12 provinsi. Survei dilakukan
secara tatap muka. Wawancara dilaksanakan pada 5 Mei 2026 hingga
28 Mei 2026. Populasi survei adalah rumah tangga dengan kepala
keluarga berusia 18 tahun ke atas di wilayah tersebut. Tingkat
kepercayaan survei ini adalah 95 persen dengan margin of error
sebesar 2,5 persen. Redaksi pertanyaan disusun oleh komite etik
lembaga. Pendana survei berasal dari hibah riset nasional.

BAB 3 HASIL SURVEI
Temuan utama menunjukkan 38,7 persen rumah tangga melaporkan kondisi
keuangan membaik dibanding tahun lalu. Sebanyak 27,4 persen
rumah tangga menyatakan pengeluaran pangan naik lebih dari 10 persen.
Indeks kepercayaan konsumen tercatat pada angka 96,2 pada Mei 2026.
Akses rumah tangga terhadap kredit formal berada di 44,1 persen,
sementara 18,9 persen rumah tangga masih bergantung pada kredit
non-formal. Kepuasan terhadap stabilitas harga kebutuhan pokok
sebesar 52,6 persen.

BAB 4 PENUTUP
Demikian laporan survei ini disampaikan. Metode dan instrumen lengkap
merupakan bagian tidak terpisah dari laporan ini.
""",
    },
    {
        "file": "literasi-digital-2026.pdf",
        "title": "Survei Literasi Digital Nasional 2026",
        "publisher": "Asosiasi Data Nusantara Contoh",
        "publication_date": "2026-08-05",
        "period_start": "2026-07-01",
        "period_end": "2026-07-20",
        "source_url": "",
        "notes": "Data sintetis untuk demonstrasi SatuSurvey. Disclosure 5/9, MoE klaim di bawah hitungan.",
        "text": """
LAPORAN SURVEI LITERASI DIGITAL NASIONAL 2026
Asosiasi Data Nusantara Contoh

BAB 1 PENDAHULUAN
Survei Literasi Digital Nasional 2026 mengukur kemampuan penduduk
menggunakan, menilai, dan mengolah informasi digital. Laporan ini
disusun oleh Asosiasi Data Nusantara Contoh.

BAB 2 METODOLOGI
Survei ini menggunakan metode multistage random sampling dengan
sampel sebanyak 1.000 responden. Survei dilakukan secara tatap muka
di 10 kota. Populasi survei adalah penduduk usia 15 tahun ke atas.
Tingkat kepercayaan survei ini adalah 95 persen dengan margin of
error sebesar 1,8 persen.

BAB 3 HASIL SURVEI
Hasil survei menunjukkan 66,3 persen responden memiliki literasi
digital pada kategori sedang ke atas. Sebanyak 49,8 persen responden
memahami konsep dasar keamanan akun, sementara hanya 23,5 persen
mampu mengenali upaya penipuan daring dalam skenario uji. Kepuasan
terhadap kualitas akses internet di wilayah tempat tinggal berada
di angka 57,2 persen. Adopsi dompet digital oleh rumah tangga
tercatat 71,4 persen.

BAB 4 PENUTUP
Demikian laporan survei ini disampaikan untuk umum.
""",
    },
    {
        "file": "kepercayaan-institusi-2026.pdf",
        "title": "Survei Kepercayaan Publik terhadap Institusi 2026",
        "publisher": "Kantor Survei Contoh",
        "publication_date": "2026-09-12",
        "period_start": "2026-08-01",
        "period_end": "2026-08-15",
        "source_url": "",
        "notes": "Data sintetis untuk demonstrasi SatuSurvey. Disclosure rendah, MoE tidak dinyatakan.",
        "text": """
LAPORAN SURVEI KEPERCAYAAN PUBLIK 2026
Kantor Survei Contoh

BAB 1 PENDAHULUAN
Survei ini mengukur kepercayaan publik terhadap berbagai institusi
nasional. Laporan ringkas disusun oleh Kantor Survei Contoh.

BAB 2 METODOLOGI
Survei dilakukan dengan penarikan sampel acak di 8 provinsi dengan
900 responden. Wawancara dilaksanakan pada Agustus 2026.

BAB 3 HASIL SURVEI
Kepercayaan publik terhadap lembaga peradilan tercatat 41,7 persen.
Kepercayaan terhadap kepolisian berada di 53,2 persen. Kepercayaan
terhadap lembaga pendidikan tinggi mencapai 68,9 persen. Separuh
responden, tepatnya 50,4 persen, merasa institusi daerah lebih
responsif dibanding sebelumnya. Kepuasan terhadap transparansi
anggaran daerah sebesar 34,6 persen.

BAB 4 PENUTUP
Demikian laporan ringkas survei ini disampaikan.
""",
    },
    {
        "file": "panel-online-hobi-digital-2026.pdf",
        "title": "Survei Panel Online Hobi Digital 2026",
        "publisher": "Riset Panel Contoh",
        "publication_date": "2026-10-02",
        "period_start": "2026-09-10",
        "period_end": "2026-09-18",
        "source_url": "",
        "notes": "Data sintetis untuk demonstrasi SatuSurvey. Sampel kuota/panel online, MoE dinyatakan.",
        "text": """
LAPORAN SURVEI PANEL ONLINE HOBI DIGITAL 2026
Riset Panel Contoh

BAB 1 PENDAHULUAN
Survei ini memetakan kebiasaan hobi digital penduduk perkotaan.
Laporan disusun oleh Riset Panel Contoh berbasis panel online.

BAB 2 METODOLOGI
Survei ini menggunakan metode kuota dengan perekrutan responden
melalui panel online. Sampel sebanyak 800 responden dipilih sesuai
kuota umur dan jenis kelamin. Survei dilakukan secara daring melalui
tautan kuesioner. Populasi survei adalah pengguna internet usia 18
sampai 45 tahun di wilayah perkotaan. Tingkat kepercayaan survei
ini adalah 95 persen dengan margin of error sebesar 3,0 persen.

BAB 3 HASIL SURVEI
Hasil menunjukkan 62,7 responden menghabiskan lebih dari dua jam
sehari untuk hobi digital. Streaming video menjadi hobi digital
paling populer dengan 78,3 persen. Bermain game daring diikuti 54,9
persen responden. Kreasi konten dilakukan 31,2 persen responden.
Kepuasan terhadap kualitas pengalaman hobi digital berada di 70,5
persen.

BAB 4 PENUTUP
Demikian laporan survei ini disampaikan.
""",
    },
    {
        "file": "pangan-rumah-tangga-2026.pdf",
        "title": "Survei Ketahanan Pangan Rumah Tangga 2026",
        "publisher": "Lembaga Studi Pangan Contoh",
        "publication_date": "2026-07-22",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "source_url": "",
        "notes": "Data sintetis untuk demonstrasi SatuSurvey. Disclosure lengkap, kepercayaan 99 persen.",
        "text": """
LAPORAN SURVEI KETAHANAN PANGAN RUMAH TANGGA 2026
Lembaga Studi Pangan Contoh

BAB 1 PENDAHULUAN
Laporan ini menyajikan hasil Survei Ketahanan Pangan Rumah Tangga
2026 yang diselenggarakan oleh Lembaga Studi Pangan Contoh.
Survei memantau akses, konsumsi, dan kecukupan pangan rum tangga.

BAB 2 METODOLOGI
Survei ini menggunakan metode two-stage cluster sampling. Sampel
sebanyak 2.000 rumah tangga dipilih secara acak dari 15 provinsi.
Survei dilakukan secara tatap muka oleh enumerator terlatih.
Wawancara dilaksanakan pada 3 Juni 2026 hingga 27 Juni 2026.
Populasi survei adalah rumah tangga dengan minimal satu anggota
berusia 18 tahun ke atas. Tingkat kepercayaan survei ini adalah
99 persen dengan margin of error sebesar 2,9 persen. Pembobotan
mengikuti proporsi rumah tangga nasional dari sensus terakhir.
Pendana survei berasal dari konsorsium riset pangan. Redaksi
pertanyaan telah melalui uji reliabilitas dan disetujui komite
etik. Seluruh rumah tangga yang disurvei memberikan persetujuan.

BAB 3 HASIL SURVEI
Temuan utama menunjukkan 45,8 persen rumah tangga menyatakan
ketahanan pangan keluarga dalam kondisi baik. Konsumsi pangan
bergizi (protein hewani minimal sekali sehari) tercatat 57,3
persen rumah tangga. Kecukupan cadangan pangan rumah tangga
selama satu minggu mencapai 62,1 persen. Kerawanan pangan
musiman dilaporkan 19,6 persen rumah tangga. Kepuasan terhadap
akses pasar pangan terdekat sebesar 68,4 persen.

BAB 4 PENUTUP
Demikian laporan survei ini disampaikan. Instrumen dan lampiran
data merupakan bagian tidak terpisah dari laporan ini.
""",
    },
]


def make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for paragraph in text.strip().split("\n"):
        lines = textwrap.wrap(paragraph, width=88) or [""]
        for line in lines:
            if y > 780:
                page = doc.new_page()
                y = 60
            page.insert_text((60, y), line)
            y += 13
        y += 8
    data = doc.tobytes()
    doc.close()
    return data


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for doc in DOCS:
        pdf_bytes = make_pdf(doc["text"])
        path = OUT_DIR / doc["file"]
        path.write_bytes(pdf_bytes)
        manifest.append(
            {
                "file": doc["file"],
                "title": doc["title"],
                "publisher": doc["publisher"],
                "publication_date": doc["publication_date"],
                "period_start": doc["period_start"],
                "period_end": doc["period_end"],
                "source_url": doc["source_url"],
                "notes": doc["notes"],
            }
        )
        print(f"{doc['file']}: {len(pdf_bytes)} bytes")
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
