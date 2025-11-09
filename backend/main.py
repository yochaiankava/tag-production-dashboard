from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import sqlite3
import io
import numpy as np
from pathlib import Path
import os
import shutil

app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Path Configuration (נתיב יחסי לקובץ שנמצא ב-Git) ---
# DB_DIR מצביע לתיקיית 'data' במאגר ה-Git, שם אמור להיות tags.db.
DB_DIR = Path("data") 

# DB_PATH הוא הנתיב המלא לקובץ ה-DB
DB_PATH = DB_DIR / "tags.db"

# EXPORT_DIR נשאר לצורך כתיבה זמנית (אחסון זמני בלבד ב-Free Tier)
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True) 

# --- Database Initialization (using 'with' statement) ---
def init_db():
    try:
        # ודא שהתיקייה 'data' קיימת (אם הגישה מ-Git כשלה, ניצור אותה)
        DB_DIR.mkdir(exist_ok=True) 
        
        with sqlite3.connect(DB_PATH) as conn:
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
    except Exception as e:
        print(f"Error during DB initialization: {e}")

init_db()

# --- Helpers ---
def extract_series(device_id: str) -> str:
    s = str(device_id).strip()
    if len(s) <= 5:
        return s[:2]
    return s[:3]

def update_series_stats():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("SELECT * FROM tags", conn)
            
            if df.empty:
                # מנקה סטטיסטיקות אם אין תגים
                conn.execute("DELETE FROM series_stats") 
                conn.commit()
                return
                
            df['production_date'] = pd.to_datetime(df['production_date'], errors='coerce')
            stats = df.groupby('series')['production_date'].agg(['count', 'min', 'max']).reset_index()
            
            def compute_expected(dates):
                dates = dates.dropna().sort_values()
                if len(dates) == 0:
                    return None
                lower = int(len(dates)*0.1)
                upper = int(len(dates)*0.9)
                trimmed = dates.iloc[lower:upper] if upper > lower else dates
                return trimmed.iloc[len(trimmed)//2]
                
            stats['expected_date'] = df.groupby('series')['production_date'].apply(compute_expected).values
            stats.rename(columns={'min': 'min_date', 'max': 'max_date'}, inplace=True)
            stats = stats.replace({np.nan: None, np.inf: None, -np.inf: None})
            
            stats.to_sql('series_stats', conn, if_exists='replace', index=False)
            conn.commit()

    except Exception as e:
        print(f"Error updating series stats: {e}")

# --- API Endpoints ---

@app.post("/upload-db")
async def upload_db(file: UploadFile = File(...)):
    contents = await file.read()
    
    # ניסיון גנרי לקרוא את הקובץ
    try:
        # קורא את הקובץ לפי סיומת או מנסה קריאת אקסל/CSV
        if file.filename.endswith(('.xlsx', '.xls')):
             df = pd.read_excel(io.BytesIO(contents), engine="openpyxl", header=None, dtype=str)
        elif file.filename.endswith(('.csv')):
             df = pd.read_csv(io.BytesIO(contents), encoding='windows-1255', header=None, dtype=str)
        else:
             # אם הסיומת לא מוכרת, ננסה קריאת אקסל כברירת מחדל
             df = pd.read_excel(io.BytesIO(contents), engine="openpyxl", header=None, dtype=str)
             
    except Exception as e:
        return {"error": f"Failed to read file: {str(e)}. Please ensure it is a valid Excel or CSV file."}

    try:
        df = df.iloc[:, [3, 24]]
    except Exception:
        return {"error": "File does not contain enough columns (need D and Y columns)"}

    df.columns = ["device_id", "production_date"]
    df = df.dropna(subset=["device_id", "production_date"])
    df["production_date"] = pd.to_datetime(df["production_date"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["production_date"])
    df["series"] = df["device_id"].astype(str).apply(extract_series)

    # שימוש ב-with לחיבור מאובטח
    with sqlite3.connect(DB_PATH) as conn:
        existing_ids = pd.read_sql_query("SELECT device_id FROM tags", conn)
        existing_ids_set = set(existing_ids["device_id"].astype(str).tolist())
        before_count = len(df)
        df = df[~df["device_id"].astype(str).isin(existing_ids_set)]
        new_count = len(df)
        skipped = before_count - new_count
        
        if new_count == 0:
            return {"message": f"No new tags added. {skipped} duplicate tags skipped."}

        # דגש: הנתונים נשמרים לקובץ tags.db שנפתח מ-Git.
        # הקובץ המעודכן יאבד ב-Restart של Render.
        df.to_sql("tags", conn, if_exists="append", index=False)
        conn.commit()

    update_series_stats()
    return {"message": f"Database updated with {new_count} new rows. {skipped} duplicates skipped."}

@app.post("/check-tags")
async def check_tags(file: UploadFile = File(...)):
    contents = await file.read()
    
    try:
        df_tags = pd.read_excel(io.BytesIO(contents), engine="openpyxl", dtype=str, header=None)
    except Exception as e:
        return {"error": f"Failed to read file. Please ensure it is an Excel file: {str(e)}"}

    df_tags = df_tags.iloc[:, [2]].dropna()
    df_tags.columns = ["device_id"]

    # שימוש ב-with לחיבור מאובטח - קורא את ה-DB המאוחסן ב-Git
    with sqlite3.connect(DB_PATH) as conn:
        df_stats = pd.read_sql_query("SELECT series, expected_date FROM series_stats", conn)
    
    df_tags["series"] = df_tags["device_id"].astype(str).apply(extract_series)
    df_result = df_tags.merge(df_stats, on="series", how="left")

    # סינון תגים לא תקינים
    df_result = df_result[df_result["device_id"].apply(
        lambda x: str(x).strip() and "allflex" not in str(x).lower() and "מספר תג" not in str(x) and str(x).isdigit()
    )]

    # ... (שאר הלוגיקה נשארה זהה)

    df_result["production_date"] = df_result["expected_date"].apply(
        lambda x: pd.to_datetime(x).strftime("%Y-%m") if pd.notna(x) else "Unknown"
    )
    df_result["status"] = df_result["expected_date"].apply(lambda x: "Known series" if pd.notna(x) else "Unknown series")
    df_result["production_year"] = df_result["expected_date"].apply(
        lambda x: pd.to_datetime(x).year if pd.notna(x) else "Unknown"
    )

    year_counts = {}
    for y in df_result["production_year"]:
        year_counts[y] = year_counts.get(y, 0) + 1
    yearly_distribution = [{"year": k, "count": v} for k, v in year_counts.items()]

    df_result = df_result.replace({np.nan: None, np.inf: None, -np.inf: None})

    return {
        "tags_count": len(df_result),
        "tags": df_result.to_dict(orient="records"),
        "yearly_distribution": yearly_distribution
    }

@app.get("/clean-duplicates")
def clean_duplicates():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT * FROM tags", conn)
        
        if df.empty:
            return {"message": "Database is empty, nothing to clean."}
        
        before = len(df)
        df = df.drop_duplicates(subset=["device_id"], keep="first")
        after = len(df)
        removed = before - after
        
        df.to_sql("tags", conn, if_exists="replace", index=False)
        conn.commit()
    
    update_series_stats()
    return {"duplicates_removed": removed, "remaining_tags": after}

@app.post("/update-series")
async def update_series(file: UploadFile = File(...)):
    contents = await file.read()
    
    try:
        df_new = pd.read_excel(io.BytesIO(contents), engine="openpyxl", dtype=str, header=None)
    except Exception as e:
        return {"error": f"Failed to read Excel file: {str(e)}"}

    df_new = df_new.iloc[:, [3, 24]].dropna()
    df_new.columns = ["device_id", "production_date"]
    df_new["production_date"] = pd.to_datetime(df_new["production_date"], errors="coerce", dayfirst=True)
    df_new = df_new.dropna(subset=["production_date"])
    df_new["series"] = df_new["device_id"].astype(str).apply(extract_series)

    with sqlite3.connect(DB_PATH) as conn:
        df_existing = pd.read_sql_query("SELECT * FROM tags", conn)
        
        merged = df_existing.drop(columns=["series"]).merge(
            df_new[["device_id", "series"]], on="device_id", how="left"
        )
        merged["series"] = merged["series_y"].combine_first(merged["series_x"])
        merged = merged[["device_id", "production_date", "series"]]
        
        merged.to_sql("tags", conn, if_exists="replace", index=False)
        conn.commit()

    update_series_stats()
    return {"message": "Series updated successfully according to new file."}

@app.get("/tags-export")
def tags_export():
    with sqlite3.connect(DB_PATH) as conn:
        df_tags = pd.read_sql_query("SELECT * FROM tags", conn)
    
    if df_tags.empty:
        return {"error": "No tags to export."}
        
    # הערה: קבצים ב-EXPORT_DIR יאבדו ב-Restart
    export_file = EXPORT_DIR / "tags_export.xlsx" 
    df_tags.to_excel(export_file, index=False)
    
    return {"file_path": f"exports/tags_export.xlsx"}

@app.get("/all-tags")
def get_all_tags():
    with sqlite3.connect(DB_PATH) as conn:
        df_tags = pd.read_sql_query("SELECT * FROM tags", conn)
        
    if df_tags.empty:
        return {"message": "Database is empty."}
        
    df_tags = df_tags.replace({np.nan: None})
    return df_tags.to_dict(orient="records")

@app.get("/series-stats")
def get_series_stats():
    with sqlite3.connect(DB_PATH) as conn:
        df_stats = pd.read_sql_query("SELECT * FROM series_stats", conn)
        
    if df_stats.empty:
        return {"message": "No series statistics available."}
        
    df_stats = df_stats.replace({np.nan: None})
    return df_stats.to_dict(orient="records")

@app.get("/yearly-distribution")
def yearly_distribution():
    with sqlite3.connect(DB_PATH) as conn:
        df_tags = pd.read_sql_query("SELECT * FROM tags", conn)
        
    if df_tags.empty:
        return {"error": "No tags in database."}
        
    df_tags['production_date'] = pd.to_datetime(df_tags['production_date'], errors='coerce')
    df_tags['year'] = df_tags['production_date'].dt.year
    df_tags['year'] = df_tags['year'].fillna("Unknown")
    yearly_dist = df_tags.groupby('year').size().reset_index(name='count')
    yearly_dist = yearly_dist.replace({np.nan: None, np.inf: None, -np.inf: None})
    return {"yearly_distribution": yearly_dist.to_dict(orient='records')}