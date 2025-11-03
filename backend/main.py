from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import sqlite3
import io
import numpy as np
from pathlib import Path

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_DIR = Path("data")
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "tags.db"

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)


# יצירת טבלאות אם לא קיימות
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        series TEXT,
        device_id TEXT PRIMARY KEY,
        production_date TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS series_stats (
        series TEXT PRIMARY KEY,
        count INTEGER,
        min_date TEXT,
        max_date TEXT,
        expected_date TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()


# פונקציית עזר – הפקת סידרה ממספר מזהה לפי הלוגיקה החדשה
def extract_series(device_id: str) -> str:
    s = str(device_id).strip()
    if len(s) <= 5:
        return s[:2]
    return s[:3]


# עדכון טבלת הסטטיסטיקות לפי הנתונים שבמסד
def update_series_stats():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM tags", conn)
    if df.empty:
        conn.close()
        return
    df['production_date'] = pd.to_datetime(df['production_date'], errors='coerce')
    stats = df.groupby('series')['production_date'].agg(['count', 'min', 'max']).reset_index()
    stats['expected_date'] = stats.apply(
        lambda row: row['max'] + (row['max'] - row['min']) / 2
        if pd.notna(row['min']) and pd.notna(row['max']) else None,
        axis=1
    )
    stats.rename(columns={'min': 'min_date', 'max': 'max_date'}, inplace=True)
    stats = stats.replace({np.nan: None, np.inf: None, -np.inf: None})
    stats.to_sql('series_stats', conn, if_exists='replace', index=False)
    conn.close()


# --- API --- #

@app.post("/upload-db")
async def upload_db(file: UploadFile = File(...)):
    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents), engine="openpyxl", header=None, dtype=str)
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(contents), encoding='windows-1255', header=None, dtype=str)
        except Exception as e:
            return {"error": f"Failed to read file: {str(e)}"}

    try:
        df = df.iloc[:, [3, 24]]
    except Exception:
        return {"error": "File does not contain enough columns (need D and Y columns)"}

    df.columns = ["device_id", "production_date"]
    df = df.dropna(subset=["device_id", "production_date"])
    df["production_date"] = pd.to_datetime(df["production_date"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["production_date"])
    df["series"] = df["device_id"].astype(str).apply(extract_series)

    # --- מניעת כפילויות בזמן העלאה --- #
    conn = sqlite3.connect(DB_PATH)
    existing_ids = pd.read_sql_query("SELECT device_id FROM tags", conn)
    existing_ids_set = set(existing_ids["device_id"].astype(str).tolist())

    before_count = len(df)
    df = df[~df["device_id"].astype(str).isin(existing_ids_set)]
    new_count = len(df)
    skipped = before_count - new_count

    if new_count == 0:
        conn.close()
        return {"message": f"No new tags added. {skipped} duplicate tags skipped."}

    df.to_sql("tags", conn, if_exists="append", index=False)
    conn.close()

    update_series_stats()

    return {"message": f"Database updated with {new_count} new rows. {skipped} duplicates skipped."}


@app.get("/clean-duplicates")
def clean_duplicates():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM tags", conn)

    if df.empty:
        conn.close()
        return {"message": "Database is empty, nothing to clean."}

    before = len(df)
    df = df.drop_duplicates(subset=["device_id"], keep="first")
    after = len(df)
    removed = before - after

    df.to_sql("tags", conn, if_exists="replace", index=False)
    conn.close()

    update_series_stats()

    return {"duplicates_removed": removed, "remaining_tags": after}


@app.post("/check-tags")
async def check_tags(file: UploadFile = File(...)):
    contents = await file.read()

    try:
        df_tags = pd.read_excel(io.BytesIO(contents), engine="openpyxl", dtype=str, header=None)
    except Exception as e:
        return {"error": f"Failed to read Excel file: {str(e)}"}

    df_tags = df_tags.iloc[:, [2]].dropna()
    df_tags.columns = ["device_id"]
    df_tags["series"] = df_tags["device_id"].astype(str).apply(extract_series)

    conn = sqlite3.connect(DB_PATH)
    df_stats = pd.read_sql_query("SELECT * FROM series_stats", conn)
    conn.close()

    df_result = df_tags.merge(df_stats, on="series", how="left")

    df_result["production_date"] = df_result["min_date"].apply(
        lambda x: pd.to_datetime(x).strftime("%Y-%m") if pd.notna(x) else "Unknown"
    )

    df_result["status"] = df_result["min_date"].apply(lambda x: "Unknown series" if x is None else "Known series")

    df_result["production_year"] = df_result["min_date"].apply(
        lambda x: pd.to_datetime(x).year if pd.notna(x) else "Unknown"
    )

    df_result = df_result.replace({np.nan: None, np.inf: None, -np.inf: None})

    year_counts = {}
    for y in df_result["production_year"]:
        key = y
        year_counts[key] = year_counts.get(key, 0) + 1

    yearly_distribution = [{"year": k, "count": v} for k, v in year_counts.items()]

    return {
        "tags_count": len(df_result),
        "tags": df_result.to_dict(orient="records"),
        "yearly_distribution": yearly_distribution
    }


@app.get("/yearly-distribution")
def yearly_distribution():
    conn = sqlite3.connect(DB_PATH)
    df_tags = pd.read_sql_query("SELECT * FROM tags", conn)
    conn.close()

    if df_tags.empty:
        return {"error": "No tags in database."}

    df_tags['production_date'] = pd.to_datetime(df_tags['production_date'], errors='coerce')
    df_tags['year'] = df_tags['production_date'].dt.year
    df_tags['year'] = df_tags['year'].fillna("Unknown")

    yearly_dist = df_tags.groupby('year').size().reset_index(name='count')
    yearly_dist = yearly_dist.replace({np.nan: None, np.inf: None, -np.inf: None})

    return {"yearly_distribution": yearly_dist.to_dict(orient='records')}


@app.get("/tags-export")
def tags_export():
    conn = sqlite3.connect(DB_PATH)
    df_tags = pd.read_sql_query("SELECT * FROM tags", conn)
    conn.close()

    if df_tags.empty:
        return {"error": "No tags to export."}

    export_file = EXPORT_DIR / "tags_export.xlsx"
    df_tags.to_excel(export_file, index=False)
    return {"file_path": f"exports/tags_export.xlsx"}


@app.get("/all-tags")
def get_all_tags():
    conn = sqlite3.connect(DB_PATH)
    df_tags = pd.read_sql_query("SELECT * FROM tags", conn)
    conn.close()

    if df_tags.empty:
        return {"message": "Database is empty."}

    df_tags = df_tags.replace({np.nan: None})
    return df_tags.to_dict(orient="records")


@app.get("/series-stats")
def get_series_stats():
    conn = sqlite3.connect(DB_PATH)
    df_stats = pd.read_sql_query("SELECT * FROM series_stats", conn)
    conn.close()

    if df_stats.empty:
        return {"message": "No series statistics available."}

    df_stats = df_stats.replace({np.nan: None})
    return df_stats.to_dict(orient="records")
