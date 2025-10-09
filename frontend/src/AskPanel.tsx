import React, { useState } from "react";

interface Result {
  [key: string]: any;
}

interface ApiResponse {
  query: string;
  cypher: string;
  results: Result[];
  note?: string;
  session_id?: string;
  used_prev_context?: boolean;
  answer?: string;
}


// ✅ 改成相对路径，由 Nginx 代理到 backend
//const API_BASE = "/api";
const API_BASE = "https://ubiquitous-umbrella-7x5q7j699grcw6xr-8002.app.github.dev";

// ✅ 改成云端香港服务器公网 IP
//const API_BASE = "http://150.109.100.16:8001";
//const API_BASE = "http://150.109.100.16:8002";
//const API_BASE = "http://0.0.0.0:8002";



// key 翻译映射
const keyMap: Record<string, string> = {
  case_id: "病例号",
  formula: "处方名称",
  method: "煎服方法",
  name: "名称",
  herb: "中药名",
  dose: "剂量",
  prep: "炮制方法",
  tongue: "舌象",
  pulse: "脉象",
  symptom: "症状",
  symptoms: "症状",
  frequency: "频次",
};

const AskPanel: React.FC = () => {
  const [query, setQuery] = useState("");
  const [data, setData] = useState<ApiResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAsk = async () => {
    if (!query.trim()) {
      setError("请输入问题再查询。");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/ask?query=${encodeURIComponent(query)}&session_id=default&dryrun=false`
      );
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} - ${res.statusText}`);
      }
      const json: ApiResponse = await res.json();
      setData(json);
    } catch (err: any) {
      setError(`请求失败: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // 渲染表格
  const renderTable = (results: Result[]) => {
    if (results.length === 0) return null;
    const keys = Object.keys(results[0]);
    return (
      <table
        border={1}
        cellPadding={6}
        style={{
          borderCollapse: "collapse",
          margin: "1em auto",
          minWidth: "600px",
          textAlign: "center",
        }}
      >
        <thead style={{ backgroundColor: "#f2f2f2" }}>
          <tr>
            {keys.map((key) => (
              <th key={key}>{keyMap[key] || key}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {results.map((row, i) => (
            <tr
              key={i}
              style={{ cursor: "default" }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#fafafa")}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "white")}
            >
              {keys.map((key) => (
                <td key={key}>
                  {Array.isArray(row[key])
                    ? row[key].map((v: any, idx: number) => (
                        <div key={idx}>{v}</div>
                      ))
                    : row[key] !== null
                    ? row[key]
                    : "-"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  // 渲染列表（单列时用）
  const renderList = (results: Result[], key: string) => {
    return (
      <ul style={{ marginTop: "1em", textAlign: "left", maxWidth: "600px" }}>
        {results.map((row, i) => (
          <li key={i} style={{ marginBottom: "4px" }}>
            {Array.isArray(row[key])
              ? row[key].join("、")
              : row[key] !== null
              ? row[key]
              : "-"}
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        marginTop: "50px",
        width: "100%",
      }}
    >
      <h2>名中医肺病诊疗案例智能问答系统</h2>

      {/* 查询栏 */}
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center" }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{
            width: "600px",
            marginRight: "10px",
            padding: "8px",
            fontSize: "16px",
          }}
          placeholder="请输入问题，如：系统中都有哪些症状？"
        />
        <button
          onClick={handleAsk}
          disabled={loading}
          style={{
            padding: "8px 16px",
            fontSize: "16px",
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "查询中..." : "查询"}
        </button>
      </div>

      {/* 错误信息 */}
      {error && <div style={{ color: "red", marginTop: "1em" }}>❌ 出错了：{error}</div>}

      {/* 查询结果 */}
      {data && (
        <div style={{ marginTop: "1em", width: "100%", textAlign: "center" }}>
          {data.results && data.results.length > 0 ? (
            <>
              <h3>查询结果（共 {data.results.length} 条）</h3>
              {Object.keys(data.results[0]).length === 1
                ? renderList(data.results, Object.keys(data.results[0])[0])
                : renderTable(data.results)}
            </>
          ) : (
            <div>{data.answer || "没有找到相关结果。"}</div>
          )}
        </div>
      )}
    </div>
  );
};

export default AskPanel;
