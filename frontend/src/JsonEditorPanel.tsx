import React, { useEffect, useState } from "react";
import Editor from "@monaco-editor/react";

const API_BASE = "https://ubiquitous-umbrella-7x5q7j699grcw6xr-8002.app.github.dev"; // ⚠️ 改成你的后端地址

const JsonEditorPanel: React.FC = () => {
  const [fileList, setFileList] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [jsonText, setJsonText] = useState<string>("{}");
  const [status, setStatus] = useState<string>("");
  const [theme, setTheme] = useState<"light" | "vs-dark">("light");

  // ✅ 加载文件列表
  useEffect(() => {
    fetch(`${API_BASE}/list_json_files`)
      .then((res) => res.json())
      .then((data) => {
        const files = Array.isArray(data)
          ? data
          : Array.isArray(data.files)
          ? data.files
          : [];
        if (files.length === 0) setStatus("⚠️ 没有找到任何 JSON 文件。");
        else {
          setFileList(files);
          setSelectedFile(files[0]);
          setStatus(`✅ 已加载 ${files.length} 个文件`);
        }
      })
      .catch((err) => setStatus(`❌ 加载文件列表失败: ${err.message}`));
  }, []);

  // ✅ 加载选中的 JSON 文件
  useEffect(() => {
    if (!selectedFile) return;
    setStatus("⏳ 正在加载文件内容...");
    fetch(`${API_BASE}/get_json?filename=${selectedFile}`)
      .then((res) => res.json())
      .then((data) => {
        setJsonText(JSON.stringify(data, null, 2)); // 自动格式化
        setStatus(`✅ 已加载 ${selectedFile}`);
      })
      .catch((err) => setStatus(`❌ 加载失败: ${err.message}`));
  }, [selectedFile]);

  // ✅ 保存修改
  const handleSave = async () => {
    try {
      const content = JSON.parse(jsonText); // 验证 JSON 是否正确
      const res = await fetch(`${API_BASE}/update_json`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: selectedFile, content }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus(`✅ 已保存 ${selectedFile}`);
    } catch (err: any) {
      setStatus(`❌ 保存失败: ${err.message}`);
    }
  };

  // ✅ 导出 JSON
  const handleExport = () => {
    const blob = new Blob([jsonText], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = selectedFile || "data.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  // ✅ 更新知识图谱
  const handleRefreshKG = async () => {
    if (!selectedFile) return;
    setStatus("⏳ 正在更新知识图谱...");
    try {
      const res = await fetch(`${API_BASE}/refresh_kg`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: selectedFile }),
      });
      const data = await res.json();
      if (res.ok) setStatus(data.message || "✅ 知识图谱更新成功");
      else setStatus(`❌ 更新失败: ${data.error || res.statusText}`);
    } catch (err: any) {
      setStatus(`❌ 更新失败: ${err.message}`);
    }
  };

  return (
    <div
      style={{
        padding: "20px",
        textAlign: "center",
        fontFamily: "Arial",
        backgroundColor: theme === "vs-dark" ? "#1e1e1e" : "#ffffff",
        color: theme === "vs-dark" ? "#eee" : "#000",
        minHeight: "100vh",
      }}
    >
      {/* 顶部栏 */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          width: "90%",
          margin: "0 auto 10px auto",
        }}
      >
        <h2 style={{ margin: 0 }}>🧩 人工审核面板</h2>
        <div>
          {/* 主题选择 */}
          <select
            value={theme}
            onChange={(e) => setTheme(e.target.value as "light" | "vs-dark")}
            style={{
              padding: "4px 10px",
              fontSize: "13px",
              borderRadius: "6px",
              border: "1px solid #aaa",
              backgroundColor: theme === "vs-dark" ? "#2c2c2c" : "#f9f9f9",
              color: theme === "vs-dark" ? "#fff" : "#000",
              marginRight: "10px",
            }}
          >
            <option value="light">🌞 浅色主题</option>
            <option value="vs-dark">🌙 暗色主题</option>
          </select>

          {/* 文件选择 */}
          <select
            value={selectedFile}
            onChange={(e) => setSelectedFile(e.target.value)}
            style={{
              padding: "4px 10px",
              fontSize: "13px",
              borderRadius: "6px",
              border: "1px solid #aaa",
            }}
          >
            {fileList.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 编辑器 */}
      <div style={{ width: "90%", margin: "auto", height: "70vh" }}>
        <Editor
          height="100%"
          defaultLanguage="json"
          value={jsonText}
          onChange={(value) => setJsonText(value || "")}
          theme={theme}
          options={{
            fontSize: 13,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            wordWrap: "on",
          }}
        />
      </div>

      {/* 底部按钮区 */}
      <div style={{ marginTop: "20px" }}>
        <button
          onClick={handleSave}
          style={{
            padding: "6px 14px",
            marginRight: "10px",
            fontSize: "14px",
            cursor: "pointer",
            borderRadius: "6px",
            border: "1px solid #999",
          }}
        >
          💾 保存修改
        </button>

        <button
          onClick={handleExport}
          style={{
            padding: "6px 14px",
            marginRight: "10px",
            fontSize: "14px",
            cursor: "pointer",
            borderRadius: "6px",
            border: "1px solid #999",
          }}
        >
          ⬇️ 导出 JSON
        </button>

        <button
          onClick={handleRefreshKG}
          style={{
            padding: "6px 14px",
            fontSize: "14px",
            cursor: "pointer",
            borderRadius: "6px",
            border: "1px solid #999",
            backgroundColor: "#f5f5f5",
          }}
        >
          ♻️ 更新知识图谱
        </button>
      </div>

      {/* 状态提示 */}
      <div
        style={{
          marginTop: "15px",
          color: status.includes("❌") ? "red" : "green",
          fontSize: "13px",
        }}
      >
        {status}
      </div>
    </div>
  );
};

export default JsonEditorPanel;
