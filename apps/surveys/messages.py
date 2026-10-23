from __future__ import annotations

from apps.surveys.models import Survey

_STATUS_MESSAGES: dict[str, str] = {
    Survey.Status.PENDING: "Berkas diterima dan menunggu diproses.",
    Survey.Status.PROCESSING: "Survei sedang dianalisis.",
    Survey.Status.COMPLETED: "Analisis selesai. Kartu survei tersedia.",
    Survey.Status.REJECTED_METADATA: (
        "Metadata laporan belum lengkap atau tidak valid. "
        "Lengkapi judul, penerbit, dan tanggal lalu coba lagi."
    ),
    Survey.Status.REJECTED_FILE: (
        "Berkas PDF ditolak. Pastikan berkas adalah PDF berbasis teks "
        "(bukan scan/foto), berukuran wajar, dan jumlah halaman sesuai batas."
    ),
    Survey.Status.FAILED_NORMALIZATION: (
        "Ekstraksi bukti dari dokumen belum berhasil dibaca. "
        "Coba unggah ulang; bila berulang, berkas mungkin bukan laporan survei."
    ),
    Survey.Status.FAILED_ANALYSIS: (
        "Penyusunan narasi analisis belum berhasil. "
        "Bukti yang terekstrak tersimpan; coba lagi nanti."
    ),
    Survey.Status.FAILED_SYSTEM: (
        "Gangguan sementara pada sistem atau layanan AI. "
        "Silakan coba lagi beberapa saat lagi."
    ),
}


def friendly_status_message(status: str) -> str:
    """Pesan ramah dan netral untuk setiap status survei."""
    return _STATUS_MESSAGES.get(status, "Status survei tidak dikenal.")
