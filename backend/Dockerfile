FROM python:3.11-slim

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- שינוי ---
# 1. העתק את הקוד הראשי (main.py, בהנחה שהוא ב-backend)
COPY backend/main.py .

# 2. העתק את תיקיית הנתונים המלאה מתיקיית השורש לתוך /app
COPY backend/data /app/data 
# -------------

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]