import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

# =========================================================
# 1. KONFIGURASI
# =========================================================
st.set_page_config(
    page_title="Pantauan Gempa Bumi Dunia (30 Hari Terakhir)",
    page_icon="🌋",
    layout="wide"
)

WITA = ZoneInfo("Asia/Makassar")
USGS_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/"
    "v1.0/summary/all_month.geojson"
)

# Refresh halaman sesuai pengaturan, jika diaktifkan
st.sidebar.title("⚙️ Pengaturan")
auto_refresh = st.sidebar.toggle(
    "Pembaruan otomatis",
    value=True
)
minimum_magnitudo = st.sidebar.slider(
    "Magnitudo minimum untuk tabel dan peta",
    min_value=0.0,
    max_value=9.0,
    value=2.5,
    step=0.5
)
jumlah_tabel = st.sidebar.slider(
    "Jumlah baris pada tabel",
    min_value=5,
    max_value=50,
    value=15,
    step=5
)

if auto_refresh:
    st_autorefresh(30000, key="gempa_refresh")

if st.sidebar.button("🔄 Muat ulang data sekarang"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption("Sumber: USGS Earthquake Hazards Program")
st.sidebar.caption("Waktu ditampilkan dalam WITA (UTC+8).")

# =========================================================
# 2. STYLE
# =========================================================
st.markdown("""
<style>
.main-title {
    font-size: 34px;
    font-weight: 800;
    margin-bottom: 4px;
}
.subtitle {
    color: #64748b;
    font-size: 15px;
    margin-bottom: 16px;
}
.metric-card {
    padding: 16px;
    border-radius: 12px;
    background-color: #f1f5f9;
    border: 1px solid #dbe3ec;
    min-height: 105px;
}
.metric-label {
    font-size: 14px;
    color: #475569;
}
.metric-value {
    font-size: 26px;
    font-weight: 800;
    color: #0f172a;
    margin-top: 5px;
}
</style>
""", unsafe_allow_html=True)


def tampilkan_kartu(label, value):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def format_waktu(value):
    if pd.isna(value):
        return "-"
    return value.strftime("%d-%m-%Y %H:%M:%S WITA")

def format_tanggal_indonesia(tanggal):
    bulan_indo = {
        1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
        5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
        9: "September", 10: "Oktober", 11: "November", 12: "Desember"
    }
    return f"{tanggal.day} {bulan_indo[tanggal.month]} {tanggal.year}"

# =========================================================
# 3. AMBIL DATA USGS
# =========================================================
@st.cache_data(ttl=30, show_spinner=False)
def fetch_earthquake_data():
    response = requests.get(USGS_URL, timeout=30)
    response.raise_for_status()
    raw_data = response.json()

    rows = []
    for item in raw_data.get("features", []):
        properties = item.get("properties", {})
        geometry = item.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []

        magnitude = properties.get("mag")
        timestamp = properties.get("time")

        if magnitude is None or timestamp is None or len(coordinates) < 3:
            continue

        waktu_utc = pd.to_datetime(timestamp, unit="ms", utc=True)
        waktu_wita = waktu_utc.tz_convert("Asia/Makassar")

        rows.append({
            "id": item.get("id"),
            "waktu_utc": waktu_utc,
            "waktu": waktu_wita,
            "lokasi": properties.get("place", "Lokasi tidak diketahui"),
            "magnitudo": float(magnitude),
            "kedalaman": float(coordinates[2]),
            "lintang": float(coordinates[1]),
            "bujur": float(coordinates[0]),
            "url": properties.get("url", "")
        })

    columns = [
        "id", "waktu_utc", "waktu", "lokasi", "magnitudo",
        "kedalaman", "lintang", "bujur", "url"
    ]
    df = pd.DataFrame(rows, columns=columns)

    if not df.empty:
        df = df.sort_values("waktu_utc", ascending=False).reset_index(drop=True)

    return df


# =========================================================
# 4. KATEGORI MAGNITUDO DAN ANALISIS IQR
# =========================================================
def kategori_magnitudo(magnitudo):
    """Kategori visual untuk dashboard, bukan kategori resmi USGS."""
    if magnitudo < 3.0:
        return "Kecil (< 3,0)"
    elif magnitudo < 5.0:
        return "Rendah-sedang (3,0 ≤ 5,0)"
    elif magnitudo < 6.0:
        return "Cukup besar (5,0 ≤ 6,0)"
    return "Besar (≥ 6,0)"


WARNA_MAGNITUDO = {
    "Kecil (< 3,0)": "#22C55E",
    "Rendah-sedang (3,0 ≤ 5,0)": "#EAB308",
    "Cukup besar (5,0 ≤ 6,0)": "#F97316",
    "Besar (≥ 6,0)": "#EF4444",
}

def analisis_iqr(df):
    """
    IQR menandai pencilan statistik pada sebaran magnitudo.
    IQR bukan metode penentu gempa aman/berbahaya.
    """
    nilai = df["magnitudo"].dropna()

    if len(nilai) < 4:
        return None

    q1 = nilai.quantile(0.25)
    q3 = nilai.quantile(0.75)
    iqr = q3 - q1
    batas_bawah = q1 - 1.5 * iqr
    batas_atas = q3 + 1.5 * iqr

    hasil = df.copy()
    hasil["kategori_iqr"] = "Rentang umum"

    kondisi_tinggi = (
        (hasil["magnitudo"] > q3)
        & (hasil["magnitudo"] <= batas_atas)
    )
    hasil.loc[kondisi_tinggi, "kategori_iqr"] = "Magnitudo relatif tinggi"

    kondisi_pencilan = (
        (hasil["magnitudo"] < batas_bawah)
        | (hasil["magnitudo"] > batas_atas)
    )
    hasil.loc[kondisi_pencilan, "kategori_iqr"] = "Pencilan magnitudo"

    return {
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "batas_bawah": batas_bawah,
        "batas_atas": batas_atas,
        "data": hasil
    }

# =========================================================
# 5. HEADER
# =========================================================

# 1. Hitung tanggal (Wajib di atas)
sekarang = datetime.now(WITA)
tanggal_akhir = sekarang.date()
tanggal_awal = tanggal_akhir - timedelta(days=30)

# 2. Tampilkan Judul Utama
st.markdown(
    '<div class="main-title">🌋 Pantauan Gempa Bumi Dunia (30 Hari Terakhir)</div>',
    unsafe_allow_html=True
)

# 3. Tampilkan Subtitle (Harus di bawah judul)
st.markdown(
    '<div class="subtitle">'
    f'Pemantauan data gempa dari <b>{format_tanggal_indonesia(tanggal_awal)} s/d {format_tanggal_indonesia(tanggal_akhir)}</b> '
    'dan analisis sebaran magnitudo menggunakan metode IQR.'
    '</div>',
    unsafe_allow_html=True
)

# 4. Tampilkan Info Waktu & Sumber
st.caption(
    f"Pembaruan halaman: "
    f"{datetime.now(WITA).strftime('%d %B %Y, %H:%M:%S WITA')}"
)
st.caption(f"Sumber data: [USGS Earthquake Feed]({USGS_URL})")

# 5. Tampilkan Info Auto Refresh (Hanya sekali saja)
if auto_refresh:
    st.caption(f"🚴 Pembaruan otomatis aktif setiap detik.")

# =========================================================
# 6. LOAD DATA
# =========================================================
try:
    with st.spinner("Mengambil data gempa dari USGS..."):
        df = fetch_earthquake_data()
except requests.RequestException:
    st.error(
        "Data gempa gagal diambil dari USGS. Periksa koneksi internet "
        "dan coba muat ulang dashboard."
    )
    st.stop()
except Exception as error:
    st.error("Terjadi kesalahan saat membaca data gempa.")
    st.caption(f"Detail teknis: {error}")
    st.stop()

if df.empty:
    st.warning("Tidak ada data magnitudo yang dapat ditampilkan.")
    st.stop()

# --- TAMBAHKAN KODE INI ---
sekarang = datetime.now(WITA)
tanggal_akhir = sekarang.date()
tanggal_awal = tanggal_akhir - timedelta(days=30) # Mundur 30 hari

# Memotong data agar hanya rentang 30 hari terakhir (Rolling Window)
df = df[(df["waktu"].dt.date >= tanggal_awal) & (df["waktu"].dt.date <= tanggal_akhir)].copy()

if df.empty:
    st.warning(f"Belum ada data gempa dari {format_tanggal_indonesia(tanggal_awal)} sampai {format_tanggal_indonesia(tanggal_akhir)}.")
    st.stop()
# --------------------------

df["kategori_magnitudo"] = df["magnitudo"].apply(kategori_magnitudo)

# =========================================================
# 7. GEMPA TERBARU
# =========================================================
st.header("📍 Gempa Terbaru")

# Ambil data yang sudah difilter oleh slider pengguna
df_filter = df[df["magnitudo"] >= minimum_magnitudo]

if df_filter.empty:
    st.warning("Tidak ada gempa yang sesuai dengan filter magnitudo minimum Anda.")
    st.stop()

terbaru = df_filter.iloc[0]
kategori = terbaru["kategori_magnitudo"]
warna = WARNA_MAGNITUDO[kategori]

col1, col2, col3 = st.columns(3)

with col1:
    tampilkan_kartu(
        "Magnitudo terbaru",
        f"{terbaru['magnitudo']:.1f}"
    )

with col2:
    tampilkan_kartu(
        "Kedalaman",
        f"{terbaru['kedalaman']:.1f} km"
    )

with col3:
    tampilkan_kartu(
        "Waktu kejadian",
        terbaru["waktu"].strftime("%d-%m-%Y %H:%M WITA")
    )

# Indikator warna kategori magnitudo
st.markdown(
    f"""
    <div style="
        background-color: {warna}20;
        border-left: 6px solid {warna};
        padding: 14px 18px;
        border-radius: 8px;
        margin: 12px 0;
    ">
        <div style="font-size:14px; color:#64748b;">
            Kategori Magnitudo
        </div>
        <div style="
            font-size:20px;
            font-weight:700;
            color:{warna};
        ">
            ● {kategori}
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

st.write(f"**Lokasi:** {terbaru['lokasi']}")

if terbaru["url"]:
    st.markdown(
        f"[Lihat detail kejadian di USGS]({terbaru['url']})"
    )

st.divider()

# =========================================================
# 8. RINGKASAN DATA 30 HARI
# =========================================================
st.header("📊 Ringkasan Gempa 30 Hari Terakhir")

c1, c2, c3, c4 = st.columns(4)
with c1:
    tampilkan_kartu("Jumlah kejadian", f"{len(df):,}")
with c2:
    tampilkan_kartu("Magnitudo maksimum", f"{df['magnitudo'].max():.1f}")
with c3:
    tampilkan_kartu("Magnitudo rata-rata", f"{df['magnitudo'].mean():.2f}")
with c4:
    tampilkan_kartu("Kedalaman rata-rata", f"{df['kedalaman'].mean():.1f} km")

st.divider()

# =========================================================
# 9. ANALISIS IQR
# =========================================================
st.header("📈 Analisis IQR Magnitudo")

st.write(
    "IQR membandingkan magnitudo setiap gempa dengan sebaran magnitudo "
    "dalam data 30 hari yang tersedia."
)

hasil_iqr = analisis_iqr(df)

if hasil_iqr is None:
    st.warning("Data kurang dari 4 kejadian sehingga analisis IQR belum ditampilkan.")
    st.stop()

q1 = hasil_iqr["q1"]
q3 = hasil_iqr["q3"]
iqr = hasil_iqr["iqr"]
batas_bawah = hasil_iqr["batas_bawah"]
batas_atas = hasil_iqr["batas_atas"]
df_iqr = hasil_iqr["data"]

jumlah_umum = (df_iqr["kategori_iqr"] == "Rentang umum").sum()
jumlah_tinggi = (df_iqr["kategori_iqr"] == "Magnitudo relatif tinggi").sum()
jumlah_pencilan = (df_iqr["kategori_iqr"] == "Pencilan magnitudo").sum()
persen_pencilan = 100 * jumlah_pencilan / len(df_iqr)

a, b, c, d = st.columns(4)
with a:
    tampilkan_kartu("Q1", f"{q1:.2f}")
with b:
    tampilkan_kartu("Q3", f"{q3:.2f}")
with c:
    tampilkan_kartu("IQR (Q3 − Q1)", f"{iqr:.2f}")
with d:
    tampilkan_kartu("Batas atas IQR", f"{batas_atas:.2f}")

st.caption(f"Batas bawah IQR: {batas_bawah:.2f}")

a, b, c = st.columns(3)
with a:
    tampilkan_kartu("Rentang umum", f"{jumlah_umum} kejadian")
with b:
    tampilkan_kartu("Magnitudo relatif tinggi", f"{jumlah_tinggi} kejadian")
with c:
    tampilkan_kartu("Pencilan magnitudo", f"{jumlah_pencilan} kejadian")

with st.expander("Apa arti hasil IQR?"):
    st.markdown(
        f"""
        - **Q1 ({q1:.2f}):** nilai kuartil pertama; sekitar 25% magnitudo
          berada pada atau di bawah nilai ini.
        - **Q3 ({q3:.2f}):** nilai kuartil ketiga; sekitar 75% magnitudo
          berada pada atau di bawah nilai ini.
        - **IQR ({iqr:.2f}):** jarak antara Q1 dan Q3, yang menunjukkan
          rentang tengah sebaran magnitudo.
        - **Batas pencilan:** nilai di bawah {batas_bawah:.2f} atau di atas
          {batas_atas:.2f} ditandai sebagai pencilan statistik.
        """
    )

st.subheader("💡 Interpretasi hasil")
if jumlah_pencilan > 0:
    st.info(
        f"Pada data 30 hari ini, **{jumlah_pencilan:,} dari {len(df_iqr):,}** "
        f"kejadian ({persen_pencilan:.1f}%) terdeteksi sebagai pencilan. "
        f"Artinya, gempa dengan magnitudo **di atas {batas_atas:.2f}** "
        "adalah kejadian yang luar biasa dan menonjol secara statistik "
        "dibandingkan ribuan gempa kecil lainnya di data ini."
    )
else:
    st.info(
        f"Pada {len(df_iqr)} kejadian yang dianalisis, tidak ada magnitudo "
        "yang melewati batas pencilan IQR."
    )

st.warning(
    "**Penting:** kategori magnitudo dan pencilan IQR bukan penilaian "
    "gempa aman atau berbahaya. Keduanya tidak mengukur tingkat kerusakan, "
    "kekuatan guncangan di suatu tempat, atau potensi tsunami."
)

# =========================================================
# 10. DISTRIBUSI & TREN MAGNITUDO (AREA CHART)
# =========================================================
st.subheader("Tren Aktivitas Gempa per Kategori (30 Hari)")
st.write("Grafik ini menunjukkan fluktuasi jumlah gempa setiap harinya. Arahkan kursor ke grafik untuk melihat detail angkanya.")

# Definisi urutan kategori
urutan_kategori = [
    "Kecil (< 3,0)",
    "Rendah-sedang (3,0 ≤ 5,0)",
    "Cukup besar (5,0 ≤ 6,0)",
    "Besar (≥ 6,0)",
]

# 1. Siapkan data
df_tren = df.copy()
df_tren["Tanggal"] = pd.to_datetime(df_tren["waktu"].dt.date) # Lebih aman untuk Plotly

# 2. Kelompokkan data
data_tren = (
    df_tren.groupby(["Tanggal", "kategori_magnitudo"])
    .size()
    .reset_index(name="Jumlah")
)

# --- ALAT PENDETEKSI 1: Cek apakah datanya ada ---
if data_tren.empty:
    st.error("Data tren kosong. Tidak ada data yang bisa digambar.")
else:
    # 3. Buat Area Chart
    fig_area = px.area(
        data_tren,
        x="Tanggal",
        y="Jumlah",
        color="kategori_magnitudo",
        color_discrete_map=WARNA_MAGNITUDO,
        category_orders={"kategori_magnitudo": urutan_kategori},
        markers=True,
        title="Fluktuasi Harian Berdasarkan Kategori Magnitudo"
    )

    # 4. Perbaiki Tampilan
    fig_area.update_layout(
        xaxis_title="Tanggal Kejadian",
        yaxis_title="Jumlah Kejadian",
        hovermode="x unified",
        margin=dict(l=0, r=0, t=40, b=0),
        legend_title_text="Kategori Magnitudo",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    # --- ALAT PENDETEKSI 2: Tampilkan grafik ---
    st.write("Menampilkan grafik...") # Teks ini harusnya muncul sebelum grafik
    st.plotly_chart(fig_area, use_container_width=True)

# =========================================================
# TABEL 10 GEMPA TERBARU (DENGAN TIME-BASED ROLLING WINDOW)
# =========================================================
st.subheader("📋 10 Gempa Bumi Terbaru")

# 1. Buat filter Rolling Window (Time-based) di sidebar (Opsional)
rentang_jam = st.sidebar.selectbox(
    "Rentang Waktu (Rolling Window)",
    options=[1, 6, 24, 720], # 720 jam = 30 hari
    index=3, # Default 30 hari
    format_func=lambda x: f"{x} jam terakhir" if x < 720 else "30 hari terakhir"
)

# 2. Filter data berdasarkan rentang waktu
sekarang = datetime.now(WITA)
batas_waktu = sekarang - timedelta(hours=rentang_jam)
df_window = df[df["waktu"] >= batas_waktu].copy()

# 3. Hitung Rolling Statistic (Rata-rata magnitudo dari 10 kejadian terakhir)
# Kita urutkan dari yang terlama ke terbaru dulu agar hitungan rolling-nya benar
df_window = df_window.sort_values("waktu", ascending=True)
df_window["rolling_mean_10"] = df_window["magnitudo"].rolling(window=10, min_periods=1).mean()

# 4. Balikkan lagi urutannya (terbaru di atas) dan ambil 10 teratas
df_10 = df_window.sort_values("waktu", ascending=False).head(10).copy()

# 5. Format waktu
df_10["waktu"] = df_10["waktu"].apply(format_waktu)

# 6. Pilih kolom dan ganti nama
tabel_10 = df_10[[
    "waktu", "lokasi", "magnitudo", "rolling_mean_10", "kedalaman", "url"
]].rename(columns={
    "waktu": "Waktu (WITA)",
    "lokasi": "Lokasi Kejadian",
    "magnitudo": "Magnitudo",
    "rolling_mean_10": "Rata-rata 10 Gempa (Rolling)",
    "kedalaman": "Kedalaman (km)",
    "url": "Tautan"
})

# 7. Tampilkan tabel interaktif
st.dataframe(
    tabel_10,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Magnitudo": st.column_config.NumberColumn(format="%.1f"),
        "Rata-rata 10 Gempa (Rolling)": st.column_config.NumberColumn(format="%.2f", help="Rata-rata magnitudo dari 10 kejadian terakhir"),
        "Kedalaman (km)": st.column_config.NumberColumn(format="%.1f km"),
        "Tautan": st.column_config.LinkColumn(
            "Tautan", 
            display_text="Buka USGS"
        )
    }
)

# =========================================================
# 13. UNDUH DATA DAN CATATAN
# =========================================================
st.download_button(
    label="⬇️ Unduh data gempa (CSV)",
    data=df_iqr.to_csv(index=False).encode("utf-8-sig"),
    file_name="data_gempa_usgs_30_hari_iqr.csv",
    mime="text/csv"
)

with st.expander("Sumber data dan rumus"):
    st.markdown(
        f"""
        **Sumber:** [USGS Earthquake Feed]({USGS_URL})

        **Periode:** feed ringkasan USGS untuk 30 hari terakhir (periode bergulir, bukan otomatis satu bulan kalender).

        **Distribusi magnitudo:** jumlah kejadian pada setiap kelompok magnitudo selama periode feed.

        **Rumus IQR:**
        - IQR = Q3 − Q1
        - Batas bawah = Q1 − 1,5 × IQR
        - Batas atas = Q3 + 3.0 × IQR

        Nilai di luar batas tersebut ditandai sebagai pencilan statistik.
        Perhitungan menggunakan semua magnitudo yang tersedia pada feed;
        filter magnitudo hanya mengubah tabel dan peta.
        """
    )

st.caption(
    "Sumber data dashboard: USGS. Dashboard ini untuk eksplorasi data; "
    "kategori magnitudo dan hasil IQR bukan prakiraan gempa atau penilaian resmi tingkat bahaya."
)
