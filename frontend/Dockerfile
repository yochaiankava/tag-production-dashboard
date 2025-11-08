# Dockerfile זה ישמש לפריסה ב-Render בלבד (Production)

# שלב 1: Build - יצירת קבצים סטטיים
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build # יצירת קבצי Production סטטיים בתיקיית dist

# שלב 2: Serve - הגשת הקבצים הסטטיים
FROM node:20-alpine
# התקנת serve ככלי להגשת הקבצים
RUN npm install -g serve
WORKDIR /usr/share/nginx/html
# העתקת התוצאה משלב ה-Build
COPY --from=build /app/dist . 

# חשיפת הפורט
EXPOSE 8080 

# פקודת ההפעלה (Render יריץ את זה)
CMD ["serve", "-s", ".", "-l", "8080"]