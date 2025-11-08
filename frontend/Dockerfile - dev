# Dockerfile ל-frontend
FROM node:20-bullseye

# תיקיית עבודה בתוך הקונטיינר
WORKDIR /app

# העתקת הקבצים של ניהול חבילות תחילה (לcache של Docker)
COPY package*.json ./

# התקנת תלותים בצורה נקייה
# אם package-lock.json לא תואם ל-package.json, הוא יעודכן אוטומטית
RUN npm install

# עכשיו מעתיקים את כל הקוד
COPY . .

# חשיפת הפורט שהיישום משתמש בו
EXPOSE 4173

# פקודה להפעלת ה-dev server עם hot reload וכניסה מכל host
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "4173"]
