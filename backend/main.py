from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import pandas as pd
import sqlite3
import io
import numpy as np
from pathlib import Path
import os
import shutil

app = FastAPI()

# --- CORS Middleware ---
# מאפשר גישה מכל דומיין (כדי שה-Frontend יוכל לתקשר עם ה-Backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Path Configuration ---
# הנתיב היחסי לתיקיית 'data' בתוך הקונטיינר (שם ה-Dockerfile מעתיק את tags.db)
DB_DIR = Path("data") 
DB_PATH = DB_DIR / "tags.db"

# EXPORT_DIR משמש לכתיבת קבצים זמניים (יאבדו ב-Restart)
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True) 

# --- Database Initialization ---
def init_db():
    # ודא שיש תיקייה 'data' בנתיב /app (נחוץ אם ה-DB לא הועתק מ-Git)
    DB_DIR.mkdir(exist_ok=True) 
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # יוצר טבלת תגים אם לא קיימת
            conn.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                series TEXT,
                device_id TEXT PRIMARY KEY,
                production_date TEXT
            )
            """)
            # יוצר טבלת סטטיסטיקות אם לא קיימת
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
        # הדפסה ללוגים של Render אם יש בעיית DB
        print(f"Error during DB initialization: {e}")

# הפעלת אתחול ה-DB בעת טעינת הקובץ
init_db()

# --- Helpers ---
def extract_series(device_id: str) -> str:
    """מחלק את מזהה ההתקן (device_id) לסדרה (Series)"""
    s = str(device_id).strip()
    if len(s) <= 5:
        return s[:2]
    return s[:3]

def update_series_stats():
    """מעדכן את טבלת הסטטיסטיקות לאחר שינוי בטבלת tags"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("SELECT * FROM tags", conn)
            
            if df.empty:
                conn.execute("DELETE FROM series_stats") 
                conn.commit()
                return
                
            df['production_date'] = pd.to_datetime(df['production_date'], errors='coerce')
            stats = df.groupby('series')['production_date'].agg(['count', 'min', 'max']).reset_index()
            
            def compute_expected(dates):
                dates = dates.dropna().sort_values()
                if len(dates) == 0:
                    return None
                # חישוב חציון (Median) גמיש (לאחר הורדת 10% משני הקצוות)
                lower = int(len(dates)*0.1)
                upper = int(len(dates)*0.9)
                trimmed = dates.iloc[lower:upper] if upper > lower else dates
                return trimmed.iloc[len(trimmed)//2]
                
            stats['expected_date'] = df.groupby('series')['production_date'].apply(compute_expected).values
            stats.rename(columns={'min': 'min_date', 'max': 'max_date'}, inplace=True)
            stats = stats.replace({np.nan: None, np.inf: None, -np.inf: None})
            
            # כתיבת הסטטיסטיקות לטבלת series_stats
            stats.to_sql('series_stats', conn, if_exists='replace', index=False)
            conn.commit()

    except Exception as e:
        print(f"Error updating series stats: {e}")

# --- API Endpoints ---

@app.get("/")
def read_root():
    """Endpoint בסיסי לבדיקת תקינות (Health Check) על ידי Render"""
    return {"status": "ok", "service": "tag-backend is running"}

@app.post("/upload-db")
async def upload_db(file: UploadFile = File(...)):
    """מעלה קובץ Excel/CSV ומעדכן את מסד הנתונים בתוכן חדש"""
    contents = await file.read()
    
    try:
        # ניסיון קריאה גנרי תוך הסתמכות על סיומת הקובץ
        if file.filename.endswith(('.xlsx', '.xls')):
             df = pd.read_excel(io.BytesIO(contents), engine="openpyxl", header=None, dtype=str)
        elif file.filename.endswith(('.csv')):
             df = pd.read_csv(io.BytesIO(contents), encoding='windows-1255', header=None, dtype=str)
        else:
             df = pd.read_excel(io.BytesIO(contents), engine="openpyxl", header=None, dtype=str)
             
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Failed to read file: {str(e)}. Please ensure it is a valid Excel or CSV file."})

    try:
        # בחירת עמודות D (אינדקס 3) ו-Y (אינדקס 24)
        df = df.iloc[:, [3, 24]]
    except Exception:
        return JSONResponse(status_code=400, content={"error": "File does not contain enough columns (need D and Y columns)"})

    df.columns = ["device_id", "production_date"]
    df = df.dropna(subset=["device_id", "production_date"])
    df["production_date"] = pd.to_datetime(df["production_date"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["production_date"])
    df["series"] = df["device_id"].astype(str).apply(extract_series)

    with sqlite3.connect(DB_PATH) as conn:
        existing_ids = pd.read_sql_query("SELECT device_id FROM tags", conn)
        existing_ids_set = set(existing_ids["device_id"].astype(str).tolist())
        before_count = len(df)
        
        # סינון תגים שכבר קיימים במסד הנתונים
        df = df[~df["device_id"].astype(str).isin(existing_ids_set)]
        new_count = len(df)
        skipped = before_count - new_count
        
        if new_count == 0:
            return {"message": f"No new tags added. {skipped} duplicate tags skipped."}

        # הוספת השורות החדשות לטבלת tags
        df.to_sql("tags", conn, if_exists="append", index=False)
        conn.commit()

    update_series_stats()
    return {"message": f"Database updated with {new_count} new rows. {skipped} duplicates skipped."}

@app.post("/check-tags")
async def check_tags(file: UploadFile = File(...)):
    """בודק קובץ תגים חדש מול הסטטיסטיקות הקיימות במסד הנתונים"""
    contents = await file.read()
    
    try:
        df_tags = pd.read_excel(io.BytesIO(contents), engine="openpyxl", dtype=str, header=None)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Failed to read file. Please ensure it is an Excel file: {str(e)}"})

    # עמודת התגים (מניחים שהיא עמודה C - אינדקס 2)
    df_tags = df_tags.iloc[:, [2]].dropna()
    df_tags.columns = ["device_id"]

    with sqlite3.connect(DB_PATH) as conn:
        df_stats = pd.read_sql_query("SELECT series, expected_date FROM series_stats", conn)
    
    df_tags["series"] = df_tags["device_id"].astype(str).apply(extract_series)
    df_result = df_tags.merge(df_stats, on="series", how="left")

    # סינון תגים לא רצויים
    df_result = df_result[df_result["device_id"].apply(
        lambda x: str(x).strip() and "allflex" not in str(x).lower() and "מספר תג" not in str(x) and str(x).isdigit()
    )]

    # ... (המשך הלוגיקה לעיבוד הנתונים והוספת שדות)

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
    """מנקה כפילויות של device_id מטבלת tags"""
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
    """עדכון סדרה של תגים קיימים על בסיס קובץ חדש (לשימוש במקרה של תיקון סדרה)"""
    contents = await file.read()
    
    try:
        df_new = pd.read_excel(io.BytesIO(contents), engine="openpyxl", dtype=str, header=None)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Failed to read Excel file: {str(e)}"})

    df_new = df_new.iloc[:, [3, 24]].dropna()
    df_new.columns = ["device_id", "production_date"]
    df_new["production_date"] = pd.to_datetime(df_new["production_date"], errors="coerce", dayfirst=True)
    df_new = df_new.dropna(subset=["production_date"])
    df_new["series"] = df_new["device_id"].astype(str).apply(extract_series)

    with sqlite3.connect(DB_PATH) as conn:
        df_existing = pd.read_sql_query("SELECT * FROM tags", conn)
        
        # מיזוג: השתמש בסדרה החדשה (series_y) אם קיימת, אחרת השתמש בישנה (series_x)
        merged = df_existing.drop(columns=["series"]).merge(
            df_new[["device_id", "series"]], on="device_id", how="left", suffixes=('_x', '_y')
        )
        merged["series"] = merged["series_y"].combine_first(merged["series_x"])
        merged = merged[["device_id", "production_date", "series"]]
        
        merged.to_sql("tags", conn, if_exists="replace", index=False)
        conn.commit()

    update_series_stats()
    return {"message": "Series updated successfully according to new file."}

@app.get("/tags-export")
def tags_export():
    """ייצוא כל נתוני התגים לקובץ Excel"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df_tags = pd.read_sql_query("SELECT * FROM tags", conn)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"DB read error: {e}"})
    
    if df_tags.empty:
        return JSONResponse(status_code=404, content={"error": "No tags to export."})
        
    export_file = EXPORT_DIR / "tags_export.xlsx" 
    df_tags.to_excel(export_file, index=False)
    
    return FileResponse(export_file, filename="tags_export.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.get("/all-tags")
def get_all_tags():
    """שולף את כל התגים במסד הנתונים"""
    with sqlite3.connect(DB_PATH) as conn:
        df_tags = pd.read_sql_query("SELECT * FROM tags", conn)
        
    if df_tags.empty:
        return {"message": "Database is empty."}
        
    df_tags = df_tags.replace({np.nan: None})
    return df_tags.to_dict(orient="records")

@app.get("/series-stats")
def get_series_stats():
    """שולף את סטטיסטיקות הסדרות (Series)"""
    with sqlite3.connect(DB_PATH) as conn:
        df_stats = pd.read_sql_query("SELECT * FROM series_stats", conn)
        
    if df_stats.empty:
        return {"message": "No series statistics available."}
        
    df_stats = df_stats.replace({np.nan: None})
    return df_stats.to_dict(orient="records")

@app.get("/yearly-distribution")
def yearly_distribution():
    """חישוב חלוקת התגים לפי שנה"""
    with sqlite3.connect(DB_PATH) as conn:
        df_tags = pd.read_sql_query("SELECT production_date FROM tags", conn)
        
    if df_tags.empty:
        return {"error": "No tags in database."}
        
    df_tags['production_date'] = pd.to_datetime(df_tags['production_date'], errors='coerce')
    df_tags['year'] = df_tags['production_date'].dt.year
    df_tags['year'] = df_tags['year'].fillna("Unknown")
    yearly_dist = df_tags.groupby('year').size().reset_index(name='count')
    yearly_dist = yearly_dist.replace({np.nan: None, np.inf: None, -np.inf: None})
    return {"yearly_distribution": yearly_dist.to_dict(orient='records')}