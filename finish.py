import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# --- Konfigurasi Halaman Streamlit ---
st.set_page_config(
    page_title="Laporan Pagu dan Realisasi KPPN Lhokseumawe",
    page_icon="💸",
    layout="wide"
)

# --- FUNGSI MEMUAT & MENGOLAH DATA ---
@st.cache_data(ttl=300, show_spinner="Memuat data terbaru...")
def load_and_process_data(sheet_url):
    try:
        # ✔️ BENAR, GANTI DENGAN BARIS INI
        # Kode ini secara "ajaib" membaca kredensial dari brankas rahasia Streamlit.
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = gc.open_by_url(sheet_url)
    except Exception as e:
        st.error(f"Gagal terhubung ke Google Sheet. Error: {e}")
        return pd.DataFrame(), pd.DataFrame()

    sheet_names = ['GRAND TOTAL', 'KAB ACEH UTARA', 'KAB BIREUN', 'LHOKSEUMAWE']
    all_data_list = []
    monthly_data_list = []
    expected_cols = {
        'GRAND TOTAL': ['NO', 'Nama KPPN', 'KDAKUN', 'NMAKUN', 'PROGRAM PENGELOLAAN', 'TAHUN', 'PAGU', 'Total', 'PERSENTASE', 'Selisih'],
        'regional': ['NO', 'NMKABKOTA', 'KDAKUN', 'NMAKUN', 'PROGRAM PENGELOLAAN', 'TAHUN', 'PAGU', 'REALISASI JANUARI', 'REALISASI FEBRUARI', 'REALISASI MARET', 'REALISASI APRIL', 'REALISASI MEI', 'REALISASI JUNI', 'REALISASI JULI', 'REALISASI AGUSTUS', 'REALISASI SEPTEMBER', 'REALISASI OKTOBER', 'REALISASI NOVEMBER', 'REALISASI DESEMBER', 'Total', 'PERSENTASE']
    }

    for name in sheet_names:
        try:
            worksheet = spreadsheet.worksheet(name)
            rows = worksheet.get_all_values()[1:]
            if not rows:
                continue
            df_raw = pd.DataFrame(rows)
            col_map = expected_cols['GRAND TOTAL'] if name == 'GRAND TOTAL' else expected_cols['regional']
            if len(df_raw.columns) != len(col_map):
                continue
            df_raw.columns = col_map
            df_raw.rename(columns={'NMAKUN': 'Jenis Belanja'}, inplace=True)

            # Data untuk line chart per bulan
            if name != 'GRAND TOTAL':
                monthly_cols = ['PROGRAM PENGELOLAAN', 'TAHUN'] + [col for col in df_raw.columns if 'REALISASI' in col and 'Total' not in col]
                monthly_df = df_raw[monthly_cols].copy()
                monthly_df['Wilayah'] = name
                monthly_data_list.append(monthly_df)

            if 'PROGRAM PENGELOLAAN' in df_raw.columns:
                df_raw['PROGRAM PENGELOLAAN'] = df_raw['PROGRAM PENGELOLAAN'].str.strip().str.upper()
            df_raw = df_raw[df_raw['Jenis Belanja'].astype(str).str.strip() != ''].copy()
            cols_to_keep = ['Jenis Belanja', 'PROGRAM PENGELOLAAN', 'TAHUN', 'PAGU', 'Total']
            df_processed = df_raw[cols_to_keep].copy()
            df_processed.rename(columns={'PAGU': 'Anggaran', 'Total': 'Realisasi'}, inplace=True)
            df_processed['Wilayah'] = name
            all_data_list.append(df_processed)
        except Exception:
            continue

    if not all_data_list:
        return pd.DataFrame(), pd.DataFrame()

    def clean_numeric(value):
        if isinstance(value, str):
            cleaned = value.replace("Rp", "").replace(",", "").replace(".", "").strip()
            return float(cleaned) if cleaned.isdigit() else 0.0
        return float(value) if pd.notna(value) else 0.0

    # Data utama
    final_data = pd.concat(all_data_list, ignore_index=True)
    for col in ['Anggaran', 'Realisasi']:
        final_data[col] = pd.to_numeric(final_data[col].apply(clean_numeric), errors='coerce')

    final_data.dropna(subset=['TAHUN', 'Anggaran', 'Realisasi'], inplace=True)
    final_data['TAHUN'] = final_data['TAHUN'].astype(int)

    # Data bulanan
    monthly_data = pd.concat(monthly_data_list, ignore_index=True) if monthly_data_list else pd.DataFrame()
    if not monthly_data.empty:
        bulan_cols = [col for col in monthly_data.columns if 'REALISASI' in col]
        for col in bulan_cols:
            monthly_data[col] = pd.to_numeric(monthly_data[col].apply(clean_numeric), errors='coerce')
        monthly_data['TAHUN'] = monthly_data['TAHUN'].astype(int)

    return final_data, monthly_data

# --- FUNGSI VISUALISASI ---
def show_pie_chart(data):
    st.subheader("🔀 Distribusi Anggaran per Program")
    fig = px.pie(
        data,
        names='PROGRAM PENGELOLAAN',
        values='Anggaran',
        color='PROGRAM PENGELOLAAN',
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Pastel
    )
    fig.update_traces(
        textposition='inside',
        textinfo='percent',
        insidetextfont=dict(color='black', size=14),
        hovertemplate=(
            "<b>%{label}</b><br><br>" +
            "Anggaran: Rp%{value:,.0f}<br>" +
            "<extra></extra>"
        )
    )
    fig.update_layout(
        showlegend=True,
        height=700,
        legend=dict(
            title="Klik untuk menyembunyikan/menampilkan:",
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5
        )
    )
    st.plotly_chart(fig, use_container_width=True)

def show_sub_detail_pie(data, monthly_data, selected_year, selected_region):
    st.subheader("📂 Sub-detail Jenis Belanja")
    unique_programs = data['PROGRAM PENGELOLAAN'].unique()
    if len(unique_programs) == 0:
        st.warning("Tidak ada program untuk ditampilkan.")
        return

    selected_program = st.selectbox("🔎 Pilih Program Pengelolaan:", options=unique_programs)

    if selected_program:
        # Pie Chart
        sub_df = data[data['PROGRAM PENGELOLAAN'] == selected_program]
        sub_summary = sub_df.groupby('Jenis Belanja')[['Anggaran', 'Realisasi']].sum().reset_index()
        sub_summary['Persentase'] = np.where(sub_summary['Anggaran'] > 0, (sub_summary['Realisasi'] / sub_summary['Anggaran']) * 100, 0)

        sub_fig = px.pie(
            sub_summary,
            names='Jenis Belanja',
            values='Anggaran',
            color='Jenis Belanja',
            color_discrete_sequence=px.colors.qualitative.Set2,
            hole=0.4,
            height=500
        )
        sub_fig.update_traces(
            hovertemplate="<b>%{label}</b><br>Anggaran: Rp%{value:,.0f}<br><extra></extra>",
            textposition='inside',
            textinfo='percent',
            textfont_size=14
        )
        sub_fig.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
            margin=dict(l=20, r=20, t=40, b=100),
            title=f"Distribusi Anggaran per Jenis Belanja<br><sup>Program: {selected_program}</sup>"
        )
        st.plotly_chart(sub_fig, use_container_width=True)

        # Tabel Data (Corrected Indentation and removed duplicate)
        display_df = sub_summary.copy()
        display_df['Anggaran'] = display_df['Anggaran'].apply(lambda x: f"Rp {x:,.0f}")
        display_df['Realisasi'] = display_df['Realisasi'].apply(lambda x: f"Rp {x:,.0f}")

        st.dataframe(
            display_df.sort_values(by='Anggaran', ascending=False),
            column_config={
                "Persentase": st.column_config.ProgressColumn(
                    "Persentase Realisasi",
                    format="%.2f%%",
                    min_value=0,
                    max_value=100
                )
            },
            use_container_width=True,
            hide_index=True
        )

def show_summary_table(data):
    st.subheader("🔢 Tabel Ringkasan Program")

    summary_df = data.groupby('PROGRAM PENGELOLAAN').agg({
        'Anggaran': 'sum',
        'Realisasi': 'sum'
    }).reset_index()

    summary_df['Persentase'] = np.where(
        summary_df['Anggaran'] > 0,
        (summary_df['Realisasi'] / summary_df['Anggaran']) * 100,
        0
    )

    display_df = summary_df.copy()
    display_df['Anggaran'] = display_df['Anggaran'].apply(lambda x: f"Rp {x:,.0f}")
    display_df['Realisasi'] = display_df['Realisasi'].apply(lambda x: f"Rp {x:,.0f}")

    st.dataframe(
        display_df.sort_values(by='Anggaran', ascending=False),
        column_config={
            "Persentase": st.column_config.ProgressColumn(
                "Persentase Realisasi",
                format="%.2f%%",
                min_value=0,
                max_value=100
            )
        },
        use_container_width=True,
        hide_index=True
    )

def show_monthly_trend(monthly_data, selected_year, selected_region):
    st.subheader("📈 Tren Realisasi Bulanan per Program")

    if monthly_data.empty:
        st.warning("Data realisasi bulanan tidak tersedia")
        return

    bulan_cols = [col for col in monthly_data.columns if 'REALISASI' in col]
    bulan_df = monthly_data[
        (monthly_data['TAHUN'] == selected_year) &
        (monthly_data['Wilayah'] == selected_region)
    ].copy()

    if bulan_df.empty:
        st.warning(f"Tidak ada data bulanan untuk {selected_region} tahun {selected_year}")
        return

    bulan_df = bulan_df.melt(id_vars=['PROGRAM PENGELOLAAN', 'TAHUN', 'Wilayah'],
                             value_vars=bulan_cols,
                             var_name='Bulan',
                             value_name='Realisasi')

    bulan_df['Bulan'] = bulan_df['Bulan'].str.replace('REALISASI ', '')
    bulan_order = ['JANUARI', 'FEBRUARI', 'MARET', 'APRIL', 'MEI', 'JUNI',
                   'JULI', 'AGUSTUS', 'SEPTEMBER', 'OKTOBER', 'NOVEMBER', 'DESEMBER']
    bulan_df['Bulan'] = pd.Categorical(bulan_df['Bulan'], categories=bulan_order, ordered=True)

    bulan_df = bulan_df.groupby(
        ['PROGRAM PENGELOLAAN', 'TAHUN', 'Wilayah', 'Bulan'],
        observed=False
    ).agg(
        Realisasi=('Realisasi', 'sum')
    ).reset_index()

    bulan_df = bulan_df.sort_values('Bulan')

    unique_programs = bulan_df['PROGRAM PENGELOLAAN'].unique()

    if len(unique_programs) == 0:
        st.warning("Tidak ada data program untuk ditampilkan.")
        return

    # --- PERUBAHAN: KOSONGKAN PILIHAN DEFAULT ---
    selected_programs = st.multiselect(
        "Pilih Program untuk Ditampilkan:",
        options=bulan_df['PROGRAM PENGELOLAAN'].unique(),
        default=[] # Diubah menjadi daftar kosong
    )
    # --------------------------------------------

    if not selected_programs:
        st.warning("Silakan pilih minimal satu program untuk menampilkan grafik.")
        return # Tampilkan peringatan jika tidak ada yang dipilih

    filtered_df = bulan_df[bulan_df['PROGRAM PENGELOLAAN'].isin(selected_programs)]

    trend_fig = px.line(
        filtered_df,
        x='Bulan',
        y='Realisasi',
        color='PROGRAM PENGELOLAAN',
        markers=True,
        title=f"Tren Realisasi Bulanan<br><sup>Wilayah: {selected_region} | Tahun: {selected_year}</sup>",
        height=600
    )

    trend_fig.update_traces(
        hovertemplate="<b>%{x}</b><br>Program: %{fullData.name}<br>Realisasi: Rp%{y:,.0f}<extra></extra>",
        line=dict(width=2.5),
        marker=dict(size=8)
    )

    trend_fig.update_layout(
        xaxis_title=None,
        yaxis_title="Realisasi (Rp)",
        yaxis_tickprefix="Rp ",
        yaxis_tickformat=",.0f",
        hovermode="closest",
        legend=dict(
            title="Program",
            orientation="h",
            yanchor="bottom",
            y=-0.3,
            xanchor="center",
            x=0.5
        )
    )

    st.plotly_chart(trend_fig, use_container_width=True)

# --- APLIKASI UTAMA ---
def main():
    st.title("💰 Laporan Pagu dan Realisasi Anggaran KPPN Lhokseumawe")

    st.markdown("""
        <style>
            .stTabs [data-baseweb="tab-list"] { display: flex; width: 100%; gap: 2px; }
            .stTabs [data-baseweb="tab"] {
                flex-grow: 1; text-align: center; height: 50px;
                white-space: pre-wrap; background-color: #F0F2F6;
                border-radius: 4px 4px 0px 0px; padding: 10px;
                font-size: 16px; font-weight: 600;
            }
            .stTabs [aria-selected="true"] { background-color: #FFFFFF; }
        </style>""", unsafe_allow_html=True)

    # You might need to create a 'google_credentials.json' file for gspread to work.
    # For now, this part will likely cause an error if the file doesn't exist.
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ayGwiw88EsyAadikJFkdPoDHS5fLbfEcC9YXsgKGm2c/edit?usp=sharing"
    df, monthly_data = load_and_process_data(SHEET_URL)

    if df.empty:
        st.warning("Gagal memuat data. Periksa kembali URL Google Sheet atau koneksi Anda.")
        st.stop()

    st.sidebar.header("🔍 Filter Data")
    selected_region = st.sidebar.selectbox("Pilih Wilayah:", options=sorted(df['Wilayah'].unique()))
    selected_year = st.sidebar.selectbox("Pilih Tahun:", options=sorted(df['TAHUN'].unique(), reverse=True))

    filtered_df = df[(df['Wilayah'] == selected_region) & (df['TAHUN'] == selected_year)]

    if filtered_df.empty:
        st.info("Tidak ada data yang tersedia untuk filter yang Anda pilih.")
        st.stop()

    total_anggaran = filtered_df['Anggaran'].sum()
    total_realisasi = filtered_df['Realisasi'].sum()
    persen_total = (total_realisasi / total_anggaran * 100) if total_anggaran > 0 else 0

    st.markdown(f"### 📊 RINGKASAN KESELURUHAN {selected_region}")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Anggaran", f"Rp {total_anggaran:,.0f}")
    col2.metric("Total Realisasi", f"Rp {total_realisasi:,.0f}")
    col3.metric("Persentase Realisasi", f"{persen_total:.1f}%")
    st.markdown("---")

    program_summary = filtered_df.groupby('PROGRAM PENGELOLAAN').agg(
        Anggaran=('Anggaran', 'sum'),
        Realisasi=('Realisasi', 'sum')
    ).reset_index()

    if not program_summary.empty:
        program_summary['Persentase'] = np.where(
            program_summary['Anggaran'] > 0,
            (program_summary['Realisasi'] / program_summary['Anggaran']) * 100,
            0
        )

    if program_summary.empty:
        st.warning("Tidak ada data program untuk ditampilkan pada filter yang dipilih.")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📊 Program Pengelolaan", "📂 Rincian Jenis Belanja", "📈 Tren Bulanan"])

    with tab1:
        st.markdown("")
        show_pie_chart(program_summary)
        st.markdown("---")
        show_summary_table(program_summary)

    with tab2:
        st.markdown("")
        show_sub_detail_pie(filtered_df, monthly_data, selected_year, selected_region)

    with tab3:
        st.markdown("")
        show_monthly_trend(monthly_data, selected_year, selected_region)

if __name__ == '__main__':
    main()
