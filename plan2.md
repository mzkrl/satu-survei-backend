# plan2.md — Inspeksi Profil & Konflik Kepentingan (Swarm Riset + Web)

Rencana lanjutan setelah `plan.md` (M0–M12). Menambah lapis **inspeksi profil**: siapa pelaksana, siapa pendana, ke mana arah kepentingan mereka — lalu menampilkan **indikator potensi konflik kepentingan** (bukan vonis) yang bisa pembaca periksa sendiri. Sumber daya: model gratis di 9router + web search Tavily.

Aturan main `CLAUDE.md` tetap berlaku penuh untuk plan ini (satu milestone per sesi, test dulu, tanpa LLM asli di test, netral, tanpa dependency baru tanpa izin, satu commit per milestone `M13: …` dst).

## 1. Konteks & tujuan

`plan.md` memverifikasi **angka** dalam survei (grounding, MoE, disclosure). Plan ini memverifikasi **profil** di balik survei:

- **Target**: pelaksana (`conducted_by`), pendana (`sponsor_or_funder`), organisasi lain yang disebut di dokumen.
- **Facet riset per target** (4 wajib): identitas | kepengurusan/pekerjaan | pendana | fokus usaha.
- **Hasil akhir per survei**:
  - Kartu profil pelaksana & pendana (tiap klaim ber-badge verifikasi + sumber).
  - Relasi sederhana: `person —works_at→ org`, `org —funded_by→ org`, `org —focuses→ sektor`.
  - Panel indikator konflik kepentingan (R3–R5, dihitung **kode**).
  - Angka kepercayaan inspeksi (% klaim didukung lintas-model).
  - Daftar hasil pencarian web yang dipakai (URL + snippet) untuk transparansi.

## 2. Prinsip (diwarisi plan.md)

1. **LLM = usulan, bukan fakta.** Setiap klaim wajib `source_type` (`pdf` | `model_knowledge` | `web`) + `source_ref`; tanpa sumber tidak ditampilkan.
2. **Sitasi keras.** Klaim `source_type=web` hanya sah jika `source_ref` ∈ daftar URL hasil search yang kita kirim ke model; kalau tidak → otomatis diturunkan ke `model_knowledge` + confidence turun.
3. **Skor dari kode, bukan LLM.** LLM mengisi entitas/relasi/klaim; R3–R6 dihitung deterministik.
4. **Bahasa netral.** Kata "bias/bohong/manipulatif/palsu" dilarang. Framing: "indikator potensi konflik kepentingan — perlu diperiksa". Disclaimer "bukan vonis" wajib di section baru.
5. **Tanpa data pribadi** di luar isi dokumen & jabatan publik (privacy).
6. **Demo & test offline**: `FakeLLMClient` + `FakeSearchClient`; cache demo per survey; `DEMO_MODE` tanpa API key.
7. **Budget ketat + degradasi anggun**: gagal riset ≠ gagal pipeline; status survei tetap `completed`, section riset tampil "inspeksi terbatas".
8. **Log hanya** `id/tahap/percobaan/kode error/usage` — isi klaim & snippet tidak pernah di-log.
9. **Biaya web sadar dana**: jumlah query search dibatasi; `usage.search_cost_usd` dicatat di provenance.
10. `schema_version` naik `1.1`. Satu commit per milestone, GPG-signed, checkbox dicentang saat selesai.

## 3. Non-goals v1

- Rekursi > 2 hop (surveyor → organisasi → pendana sudah cukup).
- Deep crawl/map situs; v1 hanya **search** + (opsional) fetch 1 halaman (`WEBFETCH_ENABLED=0` default).
- Status pipeline async (tetap sinkron di pipeline yang ada).
- Menyimpulkan "survei ini bohong/bias" — hanya indikator berbasis fakta bersumber.

## 4. Sumber daya (terverifikasi live 2026-10-28)

| Kapasitas | Endpoint | Catatan |
|---|---|---|
| Chat 47 model | `POST {BASE_URL}/v1/messages` (Anthropic-compat) | jangan hardcode nama model — validasi `/v1/models` runtime |
| Web search | `POST {BASE_URL}/v1/search` `{model:"tavily"|"exa"|"search-combo", query, max_results}` + SearxNG direct `GET {SEARXNG_URL}/search?format=json` | **OK live** (tavily ~$0.008, exa ~$0.007 per query; searxng gratis); balasan9router: `results[].{title,url,snippet}` + `usage.search_cost_usd` |
| Web fetch | `POST {BASE_URL}/v1/web/fetch` `{model:"tavily"|"exa"|"fetch-combo", url, format:"markdown", max_characters}` | terverifikasi ada; default **off** di v1 |
| Tavily REST langsung | `POST https://api.tavily.com/search` + `api_key` | **OK live** — fallback bila 9router mati |
| Exa REST langsung | `POST https://api.exa.ai/search` + header `x-api-key` | fallback bila 9router mati |

Catatan smoke test (2026-10-28): query "lembaga survei Indonesia" — exa memberi hasil organisasi lebih relevan (lsi.or.id) dibanding tavily; urutan `SEARCH_MODELS` bisa disetel sesuai kebutuhan facet.

- Base URL 9router saat ini: `http://100.115.74.9:20128/v1` (dari `ANTHROPIC_BASE_URL`); satu key yang sama dipakai untuk search/fetch (`NINEROUTER_URL` = host yang sama, tidak perlu env baru).
- **SearxNG: dipakai DIRECT (tanpa 9router), terverifikasi live.** Endpoint9router untuk searxng hardcoded `localhost:8888` + SSRF-guard9router (blokir `localhost`, `*.internal`, IPv4 privat 10/8–192.168/16; Tailscale `100.x` tidak diblokir) dan tidak bisa diganti dari UI panel — jadi jalur kita: backend panggil `SEARXNG_URL` langsung (`GET {SEARXNG_URL}/search?q=…&format=json`). Status VM (2026-10-28, via SSH `tencent`): package Ubuntu+uwsgi, `/etc/searxng/settings.yml` sudah `formats: [html, json]`, `limiter: false`; verifikasi dari luar: **37 hasil**, field `title/url/content`. Gratis unlimited — fallback ketiga setelah tavily/exa.

## 5. Env baru (semua dari env, tanpa hardcode)

```
RESEARCH_ENABLED=1
RESEARCH_MODEL_A=bzl/deepseek-v4-flash-0731free     # riset (vendor utama)
RESEARCH_MODEL_B=oc/glm-5.3-flash-free              # cross-check (vendor beda)
SYNTH_MODEL=bzl/auto:free                           # sintesis akhir
RESEARCH_MODEL_FALLBACKS=                            # dipisah koma, dipakai saat 429/error
RESEARCH_BUDGET_S=180
RESEARCH_MAX_TARGETS=3
RESEARCH_MAX_HOPS=2
RESEARCH_CALL_TIMEOUT_S=60
SEARCH_PROVIDER=ninerouter                           # ninerouter | tavily | searxng | none
SEARCH_MODELS=tavily,exa,searxng                     # urutan fallback per query:
                                                     # tavily+exa via 9router, searxng direct
SEARXNG_URL=http://100.115.74.9:8888                 # di VPS compose: http://127.0.0.1:8888
SEARCH_MAX_QUERIES=12
SEARCH_RESULTS_PER_QUERY=3
SEARCH_TIMEOUT_S=10
TAVILY_API_KEY=                                      # hanya fallback langsung; gitignored, jangan pernah di-log
EXA_API_KEY=                                         # hanya fallback langsung; gitignored, jangan pernah di-log
WEBFETCH_ENABLED=0
```

`.env.example` sudah diperbarui; key Tavily (dari user, 2026-10-28) sudah di `.env` lokal, **tidak di-commit**.

## 6. Arsitektur (tahap baru setelah analisis)

```
teks PDF → normalisasi → R1/R2 → analisis        ← plan.md, tak berubah
                 └→ tahap "research" (baru):
extract_targets     # entitas dari hasil normalisasi:
                    #   conducted_by, sponsor_or_funder, org lain yang disebut
                    #   maks RESEARCH_MAX_TARGETS, dedup, kind: org|person
research_facets     # paralel (semaphore 2–3), per target × 4 facet:
                    #   1) bangun query → SearchClient (≤2 query/facet)
                    #   2) snippet+URL disuntik ke prompt LLM
                    #   3) LLM wajib balas JSON ketat; sitasi tervalidasi
                    #   hop 2 (maks RESEARCH_MAX_HOPS): klaim penting → sub-query
cross_check         # RESEARCH_MODEL_B menilai klaim berdampak (funding/employment):
                    #   supported | contradicted | unknown + alasan ≤1 kalimat
                    #   diberi snippet yang sama bila source_type=web
synthesize          # SYNTH_MODEL rangkum → profil + relasi (pydantic)
rules_engine        # R3–R6 dihitung KODE dari entitas/relasi/klaim
```

`LLMClient` tetap satu protocol; tambah argumen `model=` per panggilan. Search & fetch tidak butuh client baru di sisi9router — satu base URL + key.

## 7. Skema data (pydantic `extra="forbid"`, gaya `schemas.py`)

```
SearchResult    {title, url, snippet, retrieved_at}
ResearchTarget  {name, kind: org|person, origin_page, origin_field}
ResearchClaim   {
                  subject, predicate, object,
                  facet: identity|employment|funding|focus,
                  hop: 1|2,
                  source_type: pdf|model_knowledge|web,
                  source_ref,                # URL / kutipan PDF / "pengetahuan model"
                  confidence: 0..1,
                  verification: {status: supported|contradicted|unknown|unchecked,
                                 by_model, reason}
                }
ResearchRelation {subject, predicate, object, claim_ids[]}
ResearchOutput  {
                  status: ok|limited|disabled,
                  targets[], claims[], relations[], search_results[],
                  models_used[], search_queries_used, search_cost_usd,
                  inspected_at
                }
ConflictIndicator {rule: R3|R4|R5, severity: info|warn, detail, claim_ids[]}
```

Penyempurnaan validasi (model_validator): `source_type=web` → `source_ref` harus berupa URL yang ada di `search_results` survei; `source_type=pdf` → wajib page+excerpt; sebaliknya `unknown` → value null.

**Penyimpanan**: model baru `ResearchResult` (OneToOne `survey`, JSONField per bagian, gaya `AnalysisResult`) + `PipelineAttempt.Stage.RESEARCH` + migration kecil. `RuleResult` untuk R3–R5 mengikuti pola R1/R2 yang sudah ada.

## 8. Aturan deterministik (kode murni, diuji tanpa LLM)

- **R3** — pendana survei == subjek yang diuntungkan temuan bernada positif → indikator `warn`.
- **R4** — pelaksana berulang didanai subjek yang sama (≥2 relasi `funded_by` dalam research graph) → indikator `warn`.
- **R5** — fokus sektor pendana cocok dengan temuan bernada positif (match sektor dari relasi `focuses`) → indikator `info`/`warn`.
- **R6 (kepercayaan)** — `confidence = supported / (supported + contradicted + unknown)`; < 0.5 → panel tampil "inspeksi belum meyakinkan"; klaim `unchecked` tidak dihitung tapi ditandai.
- Semua indikator = checklist transparan berisi `claim_ids` yang bisa diklik, bukan angka tunggal.

## 9. SearchClient & validasi sitasi

```
SearchProvider protocol:
  search(query, *, max_results) -> list[SearchResult]

Implementasi:
  NineRouterSearch   # POST {BASE_URL}/v1/search; untuk provider via 9router (tavily, exa)
  SearxNGSearch      # GET {SEARXNG_URL}/search?q=…&format=json; direct, gratis unlimited
                     #   mapper: title→title, url→url, content→snippet
                     # per query coba SEARCH_MODELS berurutan sampai ada hasil; gagal semua → fail-open
  TavilySearch       # POST https://api.tavily.com/search (fallback9router mati)
  ExaSearch          # POST https://api.exa.ai/search (fallback9router mati)
  FakeSearch         # untuk test & demo cache
```

- Urutan `SEARCH_MODELS` menentukan prioritas; boleh juga diisi `search-combo` (rantai fallback otomatis dari 9router) — tapi daftar eksplisit lebih bisa diprediksi & dicatat di provenance.

- Per target×facet: 2 query turunan (mis. `"<nama>" perusahaan pendana`, `"<nama>" yayasan profil`) → top-3 snippet → prompt.
- Batas keras `SEARCH_MAX_QUERIES` per survei; query gagal/timeout (≤10s) → skip, fail-open.
- Snippet disimpan di `research.search_results` (maks 12, snippet dipotong ≤300 karakter) — tampil di UI sebagai "sumber inspeksi".
- `WEBFETCH_ENABLED=1` nanti:ambil isi1halamanprofil pendana via `/v1/web/fetch` untuk hop 2 (di luar scope v1).

## 10. Budget, degradasi, resilience

- Total anggaran research = `RESEARCH_BUDGET_S` di luar pipeline lama; habis → `status=limited`, payload terisi sebagian, pipeline tetap `completed`.
- Panggilan riset: retry + JSON-repair (pola normalisasi), timeout `RESEARCH_CALL_TIMEOUT_S`.
- 429/error provider → fallback chain `RESEARCH_MODEL_FALLBACKS` lalu model berikutnya; tetap gagal → `status=limited`.
- `SEARCH_PROVIDER=none` atau env belum diisi → research jalan tanpa web (knowledge + cross-check saja).

## 11. API & UI

- `GET /api/surveys/{id}/` (schema 1.1) + blok `research` + `conflict_indicators` (+ `search_results`).
- Halaman detail: section "Profil & kepentingan" — kartu profil, tabel klaim + badge verifikasi, indikator R3–R5, confidence bar, daftar sumber web, disclaimer netral.
- Escape semua teks klaim (aturan7 plan utama); CSV evidence tidak berubah.

## 12. Milestones

- [ ] **M13 — Skema & rules murni**: pydantic research (termasuk validator sitasi), model DB `ResearchResult` + `Stage.RESEARCH` + migration, R3–R6 murni, `FakeSearch`, unit tests (tanpa LLM).
- [ ] **M14 — Pipeline riset**: `extract_targets`, `NineRouterSearch`/`TavilySearch`, `research_facets` paralel + sitasi tervalidasi, `cross_check`, `synthesize`, orkestrator stage `research`, budget + fallback, tests (FakeLLM + FakeSearch).
- [ ] **M15 — API & UI**: payload 1.1, section "Profil & kepentingan", disclaimer, tes web+api.
- [ ] **M16 — Demo & hardening**: 6 cache riset sintetis + seed_demo, uji live 1 survei (catat biaya search), CLAUDE.md, checkbox terakhir plan2.md.

## 13. Demo & testing

- Test selalu `FakeLLMClient` (queue per tahap) + `FakeSearch` — tidak pernah menyentuh 9router/Tavily.
- `DEMO_MODE`: hasil riset dari cache `demo/cached_research/*.json` per survey (kunci `file_sha256`, pola M10).
- Smoke live (M16, manual): 1 survei nyata → pastikan payload 1.1 utuh, biaya search tercatat, indikator tampil netral.

## 14. Risiko & mitigasi

| Risiko | Mitigasi |
|---|---|
| Model free halusinasi nama/org/URL | sitasi keras dari daftar URL search; cross-check vendor beda; "unknown" sah & tampil |
| Latensi meledak (10+ panggilan) | fan-out paralel kecil, facet wajib only, budget 180s, degrade `limited` |
| Fitnah/defamation | netral + sumber + disclaimer; tanpa data pribadi |
| 9router/Tavily mati di tengah demo | fallback chain model; `status=limited`; cache demo sebagai jaring pengaman terakhir |
| Model list / konektor berubah | validasi runtime `/v1/models` + `/v1/models/web`, env-driven |
| Biaya search tak terkendala | `SEARCH_MAX_QUERIES` + catatan `search_cost_usd` di provenance |

## 15. Catatan operasional & lingkungan (2026-10-28)

- Key Tavily & Exa (user, 2026-10-28) disimpan di `.env` (`TAVILY_API_KEY`, `EXA_API_KEY`); **jangan commit, jangan log, jangan tampilkan** di UI/payload. Jalur utama lewat9router (key provider dipegang panel9router), key lokal hanya fallback langsung.
- SearxNG: kasus selesai (2026-10-28). "Blocked URL: internal host" = SSRF-guard9router terhadap endpoint hardcoded `localhost:8888`; UI panel tidak menyediakan edit → jalur9router dibuang. Direct ke `SEARXNG_URL` terverifikasi OK (json aktif, limiter false, 37 hasil). Catatan: port8888 hanya terbuka di jaringan tailscale (publik timeout) — backend lokal pakai `http://100.115.74.9:8888`, container di VPS yang sama pakai `http://127.0.0.1:8888`.
- Pengetahuan yang dipakai: skill Tavily agent-setup (integrasi aplikasi = REST/SDK, kredensial di mekanisme secret proyek, smoke test 1 request live) dan skill 9router `web-search`/`web-fetch` (bentuk endpoint & response ada di §4).
- `LLM_MODEL` lama tetap untuk tahap lama; riset memakai `RESEARCH_MODEL_*` — jangan campur.
