FROM node:20-bullseye

WORKDIR /app
COPY package*.json ./
RUN npm install
# נתקין את הספריות החסרות לבניית הגרף והורדת הקובץ
RUN npm install react-chartjs-2 chart.js file-saver
RUN npm install xlsx
COPY . .
RUN npm run build

EXPOSE 4173
CMD ["npm", "run", "preview", "--", "--host"]
