import { useState } from "react";

export default function CheckTagsTable() {
  const [file, setFile] = useState(null);
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const uploadFile = async () => {
  if (!file) return;
  setLoading(true);

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("http://localhost:8000/check-tags", {
      method: "POST",
      body: formData,
    });
    const json = await res.json();
    if (json.tags) setData(json.tags);
    else alert(json.error || "No data returned");
  } catch (err) {
    console.error(err);
    alert("Error fetching data");
  } finally {
    setLoading(false);
  }
};


  return (
    <div>
      <h1>Check Tags</h1>
      <input type="file" onChange={handleFileChange} />
      <button onClick={uploadFile} disabled={loading}>
        {loading ? "Loading..." : "Upload & Check"}
      </button>

      {data.length > 0 && (
        <table border="1" style={{ marginTop: 20 }}>
          <thead>
            <tr>
              {Object.keys(data[0]).map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i}>
                {Object.values(row).map((val, j) => (
                  <td key={j}>{val}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
