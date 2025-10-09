import React, { useEffect, useState } from "react";
import AskPanel from "./AskPanel";
import JsonEditorPanel from "./JsonEditorPanel";

// const API_BASE = "https://ubiquitous-umbrella-7x5q7j699grcw6xr-8002.app.github.dev";
const API_BASE =
  process.env.REACT_APP_API_BASE || "https://tcm-backend-nxdi.onrender.com";



const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"ask" | "editor">("ask");
  const [status, setStatus] = useState<"checking" | "online" | "offline">("checking");

  // ✅ 定期检测后端状态
  const checkServer = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (res.ok) {
        setStatus("online");
        return;
      }
      throw new Error("Health check failed");
    } catch {
      // 如果没有 /health，就尝试 /ask?query=ping
      try {
        const res2 = await fetch(`${API_BASE}/ask?query=ping`);
        setStatus(res2.ok ? "online" : "offline");
      } catch {
        setStatus("offline");
      }
    }
  };

  useEffect(() => {
    checkServer(); // 启动时立即检测
    const timer = setInterval(checkServer, 10000); // 每10秒重试
    return () => clearInterval(timer);
  }, []);

  // ✅ 状态灯样式
  const renderStatus = () => {
    const color =
      status === "online" ? "limegreen" : status === "offline" ? "red" : "gold";
    const text =
      status === "online" ? "在线" : status === "offline" ? "离线" : "检测中...";
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          fontSize: "14px",
          color: "#fff",
        }}
      >
        <span
          style={{
            width: "10px",
            height: "10px",
            borderRadius: "50%",
            backgroundColor: color,
            display: "inline-block",
          }}
        ></span>
        {text}
      </div>
    );
  };

  return (
    <div style={{ fontFamily: "Arial, sans-serif", width: "100%", minHeight: "100vh" }}>
      {/* ✅ 顶部导航栏 */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          backgroundColor: "#1e90ff",
          color: "white",
          padding: "12px 20px",
          fontSize: "18px",
          fontWeight: "bold",
          boxShadow: "0 2px 6px rgba(0,0,0,0.1)",
        }}
      >
        <nav style={{ display: "flex", gap: "40px" }}>
          <span
            style={{
              cursor: "pointer",
              borderBottom: activeTab === "ask" ? "3px solid #fff" : "none",
              paddingBottom: "4px",
            }}
            onClick={() => setActiveTab("ask")}
          >
            💬 智能问答
          </span>
          <span
            style={{
              cursor: "pointer",
              borderBottom: activeTab === "editor" ? "3px solid #fff" : "none",
              paddingBottom: "4px",
            }}
            onClick={() => setActiveTab("editor")}
          >
            🧩 人工审核
          </span>
        </nav>

        {/* ✅ 右上角服务器状态 */}
        {renderStatus()}
      </header>

      {/* ✅ 主体内容区域 */}
      <main style={{ paddingTop: "20px" }}>
        {activeTab === "ask" ? <AskPanel /> : <JsonEditorPanel />}
      </main>
    </div>
  );
};

export default App;
