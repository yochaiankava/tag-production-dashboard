import React, { useState, useRef } from "react";
import axios from "axios";
import { Pie } from "react-chartjs-2";
import { saveAs } from "file-saver";
import * as XLSX from "xlsx";
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from "chart.js";
import ChartDataLabels from "chartjs-plugin-datalabels";

ChartJS.register(ArcElement, Tooltip, Legend, ChartDataLabels);

function App() {
  const [dbFile, setDbFile] = useState(null);
  const [tagsFile, setTagsFile] = useState(null);
  const [tagsTable, setTagsTable] = useState([]);
  const [yearlyDistribution, setYearlyDistribution] = useState([]);
  const [message, setMessage] = useState("");
  const [visibleTotal, setVisibleTotal] = useState(0);

  const pieRef = useRef(null);

  // ✅ העלאת בסיס נתונים
  const handleDbUpload = async () => {
    if (!dbFile) return alert("Select a database Excel file first.");
    const formData = new FormData();
    formData.append("file", dbFile);
    try {
      //const res = await axios.post("http://localhost:8000/upload-db", formData);
	  const res = await axios.post("https://tag-backend-row3.onrender.com", formData);
      setMessage(res.data.message);
    } catch (err) {
      console.error(err);
      alert("Error uploading database.");
    }
  };

  // ✅ בדיקת תגיות
  const handleTagsCheck = async () => {
    if (!tagsFile) return alert("Select a tags Excel file first.");
    const formData = new FormData();
    formData.append("file", tagsFile);
    try {
      const res = await axios.post("http://localhost:8000/check-tags", formData);
      setMessage(`Checked ${res.data.tags_count} tags`);

      let tags = res.data.tags.map(tag => ({
        device_id: tag.device_id,
        production_date: tag.production_date ? tag.production_date : "Unknown",
      }));

      // ✅ סינון רשומות לא תקינות (כוללות טקסט או Allflex)
      tags = tags.filter(tag => {
        const id = (tag.device_id || "").toString().toLowerCase();
        return (
          id &&
          !id.includes("allflex") &&
          !id.includes("מספר תג") &&
          /^[0-9]+$/.test(id)
        );
      });

      // המרת תאריך ל־YYYY-MM
      tags = tags.map(tag => {
        if (tag.production_date !== "Unknown") {
          const d = new Date(tag.production_date);
          if (!isNaN(d)) {
            const month = (d.getMonth() + 1).toString().padStart(2, "0");
            tag.production_date = `${d.getFullYear()}-${month}`;
          } else {
            tag.production_date = "Unknown";
          }
        }
        return tag;
      });

      // מיון לפי תאריך
      tags.sort((a, b) => {
        if (a.production_date === "Unknown") return 1;
        if (b.production_date === "Unknown") return -1;
        return new Date(a.production_date) - new Date(b.production_date);
      });

      setTagsTable(tags);

      // פילוח לפי שנה
      const yearCounts = {};
      tags.forEach(tag => {
        const year =
          tag.production_date === "Unknown"
            ? "Unknown"
            : tag.production_date.split("-")[0];
        yearCounts[year] = (yearCounts[year] || 0) + 1;
      });
      const yearlyDist = Object.entries(yearCounts).map(([year, count]) => ({
        year,
        count,
      }));
      setYearlyDistribution(yearlyDist);
      setVisibleTotal(
        yearlyDist.reduce((sum, d) => sum + d.count, 0)
      );
    } catch (err) {
      console.error(err);
      alert("Error checking tags.");
    }
  };

  // ✅ ייצוא לאקסל בלבד
  const handleExport = () => {
    if (tagsTable.length === 0) {
      alert("No data to export.");
      return;
    }

    const worksheet = XLSX.utils.json_to_sheet(tagsTable);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Tags");

    const excelBuffer = XLSX.write(workbook, {
      bookType: "xlsx",
      type: "array",
    });
    const blob = new Blob([excelBuffer], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    saveAs(blob, "tags_export.xlsx");
  };

  // ✅ הורדת גרף כ־PNG עם רקע לבן
  const handleDownloadChart = () => {
    if (!pieRef.current) {
      alert("Chart not available yet.");
      return;
    }

    const chart = pieRef.current;
    const canvas = chart.canvas;
    const whiteBackground = document.createElement("canvas");
    whiteBackground.width = canvas.width;
    whiteBackground.height = canvas.height;
    const ctx = whiteBackground.getContext("2d");

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(canvas, 0, 0);

    const imageURL = whiteBackground.toDataURL("image/png");
    const link = document.createElement("a");
    link.href = imageURL;
    link.download = "yearly_distribution.png";
    link.click();
  };

  // ✅ פונקציה ליצירת צבעים שונים לכל פלח
  const generateColors = (count) => {
    const colors = [];
    for (let i = 0; i < count; i++) {
      const hue = (i * 360) / count;
      colors.push(`hsl(${hue}, 70%, 60%)`);
    }
    return colors;
  };

  // ✅ נתוני גרף
  const pieData = {
    labels: yearlyDistribution.map((d) => `${d.year}: ${d.count} תגים`),
    datasets: [
      {
        label: "Tags per Year",
        data: yearlyDistribution.map((d) => d.count),
        backgroundColor: generateColors(yearlyDistribution.length),
      },
    ],
  };

  // ✅ הגדרות גרף
  const pieOptions = {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: 30 },
    plugins: {
      tooltip: {
        callbacks: {
          label: function (context) {
            const label = context.label;
            const count = context.raw;
            const chart = context.chart;
            const data = chart.data.datasets[0].data;
            const total = data.reduce(
              (a, b, idx) =>
                chart.getDatasetMeta(0).data[idx].hidden ? a : a + b,
              0
            );
            const percentage = ((count / total) * 100).toFixed(1);
            return `${label} (${percentage}%)`;
          },
        },
      },
      legend: {
        position: "bottom",
        labels: {
          generateLabels: function (chart) {
            const data = chart.data;
            if (data.labels.length && data.datasets.length) {
              return data.labels.map((label, i) => {
                const meta = chart.getDatasetMeta(0);
                const hidden = meta.data[i].hidden === true;
                const color = data.datasets[0].backgroundColor[i];
                return {
                  text: hidden ? `❌ ${label}` : `✅ ${label}`,
                  fillStyle: color,
                  hidden: hidden,
                  strokeStyle: "#ccc",
                  lineWidth: hidden ? 2 : 0,
                  index: i,
                };
              });
            }
            return [];
          },
        },
        onClick: (evt, legendItem, legend) => {
          const chart = legend.chart;
          const index = legendItem.index;
          const meta = chart.getDatasetMeta(0);
          meta.data[index].hidden = !meta.data[index].hidden;
          chart.update();

          const visibleSum = meta.data.reduce(
            (sum, el, i) =>
              el.hidden ? sum : sum + chart.data.datasets[0].data[i],
            0
          );
          setVisibleTotal(visibleSum);
        },
      },
      datalabels: {
        color: "#000",
        anchor: "center",
        align: "center",
        font: { weight: "bold", size: 16 },
        formatter: (value, ctx) => {
          const chart = ctx.chart;
          const meta = chart.getDatasetMeta(0);
          const data = chart.data.datasets[0].data;
          const total = data.reduce((a, b, i) =>
            meta.data[i].hidden ? a : a + b, 0);
          const percent = (value / total) * 100;
          if (meta.data[ctx.dataIndex].hidden || percent < 5) return "";
          const year = yearlyDistribution[ctx.dataIndex].year;
          return `${year}\n${value} תגים`;
        },
      },
    },
  };

  // ✅ עיצוב אחיד לכפתורים
  const buttonStyle = {
    backgroundColor: "#1976d2",
    color: "white",
    border: "none",
    borderRadius: "6px",
    padding: "10px 16px",
    margin: "8px",
    cursor: "pointer",
    fontWeight: "bold",
    transition: "all 0.3s",
  };

  const buttonHover = (e) => (e.target.style.backgroundColor = "#1259a1");
  const buttonLeave = (e) => (e.target.style.backgroundColor = "#1976d2");

  return (
    <div
      style={{
        padding: 20,
        fontFamily: "Segoe UI, sans-serif",
        backgroundColor: "#f8f9fa",
        minHeight: "100vh",
      }}
    >
      <h1 style={{ textAlign: "center", color: "#333" }}>
        Tag Production Dashboard
      </h1>

      <div style={{ marginBottom: 20, textAlign: "center" }}>
        <h2>1. Upload Database</h2>
        <input type="file" onChange={(e) => setDbFile(e.target.files[0])} />
        <button
          style={buttonStyle}
          onMouseEnter={buttonHover}
          onMouseLeave={buttonLeave}
          onClick={handleDbUpload}
        >
          Upload Database
        </button>
      </div>

      <div style={{ marginBottom: 20, textAlign: "center" }}>
        <h2>2. Check Tags</h2>
        <input type="file" onChange={(e) => setTagsFile(e.target.files[0])} />
        <button
          style={buttonStyle}
          onMouseEnter={buttonHover}
          onMouseLeave={buttonLeave}
          onClick={handleTagsCheck}
        >
          Check Tags
        </button>
      </div>

      {/* ✅ מציג הודעות רגילות בלבד — לא כאלה עם ⚠️ */}
      {message && !message.includes("⚠️") && (
        <div style={{ textAlign: "center", marginBottom: 10 }}>
          <p>
            <b>Status:</b> {message}
          </p>
        </div>
      )}

      {tagsTable.length > 0 && (
        <div style={{ textAlign: "center", marginBottom: 30 }}>
          <button
            style={buttonStyle}
            onMouseEnter={buttonHover}
            onMouseLeave={buttonLeave}
            onClick={handleExport}
          >
            💾 Export Tags to Excel
          </button>
        </div>
      )}

      {yearlyDistribution.length > 0 && (
        <div
          style={{
            position: "absolute",
            top: 20,
            right: 20,
            width: "600px",
            height: "600px",
            backgroundColor: "#fff",
            borderRadius: "12px",
            boxShadow: "0 0 15px rgba(0,0,0,0.15)",
            padding: "20px",
          }}
        >
          <h3 style={{ textAlign: "center", marginTop: 0 }}>
            Yearly Distribution
          </h3>
          <p style={{ textAlign: "center", margin: 0 }}>
            <b>Visible tags in chart:</b> {visibleTotal}
          </p>
          <div style={{ width: "100%", height: "500px" }}>
            <Pie ref={pieRef} data={pieData} options={pieOptions} />
          </div>
          <div style={{ textAlign: "center", marginTop: 10 }}>
            <button
              style={buttonStyle}
              onMouseEnter={buttonHover}
              onMouseLeave={buttonLeave}
              onClick={handleDownloadChart}
            >
              📊 Download Chart as PNG
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
