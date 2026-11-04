# Video Engine

Private workflow untuk membuat video, menyimpan hasil sebagai artifact, dan mengirimnya ke Social AI Scheduler (SAS).

Untuk AI agent yang menjalankan dan memantau GitHub Actions, ikuti [AGENT_GUIDE.md](AGENT_GUIDE.md). Panduan tersebut berisi input workflow, cara dispatch via `gh` atau REST API, cara memeriksa hasil, dan aturan agar tidak membuat posting duplikat.

## Sebelum menjalankan

Di GitHub, buka **Settings → Secrets and variables → Actions**.

Tambahkan repository secrets:

- `OPENAI_API_KEY` — API key untuk model OpenAI-compatible.
- `SCHEDULER_API_BASE_URL` — alamat lengkap API SAS, misalnya `https://sas.example.com` (tanpa path `/api/direct-post`).
- `SCHEDULER_API_KEY` — API key SAS.
- `SCHEDULER_PLATFORM` — `FACEBOOK`, `INSTAGRAM`, atau `YOUTUBE`.
- `SCHEDULER_ACCOUNT_ID` — ID akun tujuan di SAS.

Opsional, tambahkan Actions variables:

- `OPENAI_BASE_URL` — default `https://ollama.com/v1`.
- `OPENAI_MODEL` — default `gemma4:cloud`.

Simpan semua credential sebagai **Secrets**, jangan taruh API key di file JSON atau workflow.

## Menjalankan manual

Buka tab **Actions → Universal video render → Run workflow**.

Pilih salah satu mode:

- **generate** — isi `brief`, lalu pilih bahasa, format, niche, scene, karakter, dan target durasi. AI membuat dialog serta CTA yang sesuai konteks.
- **job** — gunakan JSON yang sudah dibuat. Isi `job_b64` dengan Base64 dari file JSON. Input lainnya tidak membuat ulang isi job; `target_duration_seconds` hanya dipakai jika JSON belum punya nilai durasi.

Untuk mencoba job contoh dari terminal Mac, jalankan dari folder repository:

```sh
base64 < examples/universal-job.json | tr -d '\n' | pbcopy
```

Perintah itu menyalin teks Base64 ke clipboard. Tempel **hasil yang tersalin** ke kolom `job_b64` di GitHub, bukan perintahnya.

`config/scheduled-job.json` **bukan** job siap-render: isinya brief dan pilihan untuk AI pembuat job. Jangan encode file itu ke `job_b64`. Untuk mencoba konfigurasi tersebut secara manual, pilih mode **generate** lalu salin nilai `brief`, `language`, `format`, `target_duration_seconds`, `niche`, `scene`, dan `cast` ke input workflow. Untuk mode **job**, gunakan file job lengkap seperti `examples/universal-job.json`. Jadwal membaca `config/scheduled-job.json` otomatis; perubahan file itu perlu di-commit ke branch default.

`publish` menentukan apakah run manual mengirim hasil ke SAS. Jika tidak dicentang, video hanya dibuat dan disimpan sebagai artifact. Run terjadwal mengirim ke SAS otomatis.

## Hasil

Setelah workflow selesai, buka halaman run lalu bagian **Artifacts** untuk mengunduh MP4 dan `job.json`. Artifact tersedia selama 7 hari.

## Jadwal otomatis

Jadwal ada di `.github/workflows/universal-render.yml` pada bagian `schedule`. Nilai cron menggunakan zona waktu yang ditulis di sana. Scheduled workflow harus ada di branch default dan dijalankan dari versi workflow terbaru di branch tersebut. Run terjadwal memakai `config/scheduled-job.json` lalu mengirim video ke SAS.

## Menjalankan lokal

Butuh Python 3.11, FFmpeg, dan `OPENAI_API_KEY` di environment. Contoh membuat JSON job:

```sh
python generate_job.py --config config/scheduled-job.json --output /tmp/job.json
```

Lihat `examples/` untuk contoh JSON lainnya.
