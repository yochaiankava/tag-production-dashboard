Tag Production WebApp

פרויקט לניהול ובדיקת תגיות עם Backend (FastAPI + SQLite) ו‑Frontend (React + Vite), כולל Docker ו‑Docker Compose להרצה מקומית ופרודקשן.

📁 מבנה הפרויקט
tag-production-webapp/
│
├─ backend/          # FastAPI backend
│   ├─ main.py
│   ├─ data/         # מסד הנתונים SQLite
│   └─ requirements.txt
│
├─ frontend/         # React + Vite frontend
│   ├─ src/
│   ├─ package.json
│   └─ vite.config.js
│
├─ docker-compose.yml           # גרסת ברירת מחדל (dev)
├─ docker-compose.prod.yml      # גרסת פרודקשן
├─ docker-compose.dev.yml       # גרסת פיתוח
├─ .env                        # משתני סביבה
└─ README.md

🌱 משתני סביבה (.env)

צור קובץ .env בתיקייה הראשית:

ENVIRONMENT=development   # או production
BACKEND_PORT=8000
FRONTEND_PORT=4173


ENVIRONMENT – מגדיר את סביבת ההרצה (development או production)

BACKEND_PORT – פורט שבו ה‑backend יהיה זמין

FRONTEND_PORT – פורט שבו ה‑frontend יהיה זמין (dev mode בלבד)

🐳 הרצה עם Docker Compose
סביבת פיתוח מקומית
docker-compose --env-file .env up --build


Frontend ב‑dev mode עם hot reload

Backend עם reload אוטומטי

גישה ל‑Frontend: http://localhost:4173

FastAPI docs: http://localhost:8000/docs

פרודקשן (Render / VPS / Production)
ENVIRONMENT=production BACKEND_PORT=8000 FRONTEND_PORT=80 docker-compose -f docker-compose.prod.yml up --build


Frontend מגיש את קבצי dist עם npx serve

Backend מגיב על פורט 8000

גישה ל‑Frontend: http://<server-ip>/

גישה ל‑API: http://<server-ip>:8000

פקודות שימושיות
# עצירת כל containers
docker-compose down

# בניית containers בלבד
docker-compose build

# בדיקה של containers רצים
docker ps

# צפייה בלוגים
docker-compose logs -f

🖥️ Backend
התקנה והרצה ללא Docker
cd backend
python -m venv venv
# Linux / Mac
source venv/bin/activate
# Windows
venv\Scripts\activate

pip install -r requirements.txt
uvicorn main:app --reload


FastAPI docs: http://127.0.0.1:8000/docs

API Endpoints עיקריים
Endpoint	Method	Description
/upload-db	POST	העלאת קובץ Excel למסד הנתונים
/check-tags	POST	בדיקת תגיות מול מסד הנתונים
/clean-duplicates	GET	ניקוי כפילויות
/series-stats	GET	סטטיסטיקות לפי Series
🌐 Frontend
התקנה והרצה ללא Docker
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 4173


Build לפרודקשן:

npm run build
npx serve -s dist -l 80

Dashboard

Yearly Distribution Pie Chart – חלוקת התגים לפי שנה, hover על פלח מציג אחוזים, ניתן להוריד גרף כ‑PNG

Tags Table – מציג את כל התגים שהועלו, עם אפשרות לסינון ומיון לפי תאריך, וייצוא ל‑Excel

🗃️ מסד הנתונים

נשמר ב־backend/data/tags.db

קובצי Excel צריכים להכיל את השדות הבאים:

Device ID (מספר סידורי של התג)

Production Date (תאריך ייצור בפורמט YYYY-MM-DD)

🔧 טיפים

בפיתוח מקומי השתמש ב‑volumes ל‑live reload

בפרודקשן שמור על .env מתאים כדי לא לשנות קובץ ראשי

ניתן לשנות פורטים לפי צורך באמצעות משתני סביבה

הקפד להתקין את כל התלויות Python ו‑npm לפני הפעלה

📌 הערות

סביבת פיתוח משתמשת ב‑React dev server ל‑hot reload

פרודקשן מגיש את קבצי ה‑frontend דרך npx serve -s dist

ניתן להוסיף API נוסף לסטטיסטיקות או ניהול תגיות לפי צורך