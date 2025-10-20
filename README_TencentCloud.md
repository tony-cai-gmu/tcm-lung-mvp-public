# 🚀 腾讯云部署说明

本项目说明如何在腾讯云服务器上完成中医智能问答系统（后端 + 前端 + Neo4j）的完整部署。

---

## 1️⃣ 克隆项目并准备环境文件

```bash
git clone <你的 GitHub 仓库地址>
cd tcm-lung-mvp-public
```

在项目根目录创建 `.env` 文件（必须手动添加），内容示例：

```bash
# ====== Neo4j 数据库配置 ======
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASS=test123

# ====== 大模型配置 ======
OPENAI_MODEL=gpt-4o-mini    # 替换为GLM的模型
OPENAI_API_KEY=sk-xxxxxxx   # ⚠️ 替换为真实 key
```



---

## 2️⃣ 安装并启动 Docker 环境

在腾讯云 Ubuntu 服务器执行：

```bash
sudo apt update
sudo apt install docker.io docker-compose -y
sudo systemctl start docker
sudo systemctl enable docker
```

> 💡 如果项目包含 `docker-compose.yml` 文件，可直接运行：
> ```bash
> sudo docker compose up -d
> ```
> 自动启动后端和数据库服务。

---

## 3️⃣ 安装 Python 依赖（非容器部署时）

如果你手动运行后端：
```bash
pip install -r requirements.txt
```

---

## 4️⃣ 启动 Neo4j 并导入 JSON 数据

确保 Neo4j 已正常运行，访问：
```
http://<服务器IP>:7474
```
即可进入控制台。

导入病例数据：
```bash
python import_cases.py
```

> 💡 该脚本会自动读取 `/json_data/` 文件夹并将病例信息导入 Neo4j。

---

## 5️⃣ 修改端口与安全组

后端服务使用：
```bash
uvicorn app:app --host 0.0.0.0 --port 8001
```

前端默认端口为 **3000**。

> ⚙️ 请在腾讯云控制台 → 安全组中放行：
> - TCP 8001（后端 API）
> - TCP 3000（前端网页）
> - TCP 7474（Neo4j 可视化，若需要）

---

## 6️⃣ 启动前端服务

进入前端目录：
```bash
cd frontend
npm install
```

编辑 `src/AskPanel.tsx` 文件，修改为服务器实际 IP：
```ts
const API_BASE = "http://<你的腾讯云公网IP>:8001";
```

启动前端：
```bash
npm run dev
```

浏览器访问：
```
http://<你的公网IP>:3000
```

---

## 7️⃣ 测试后端接口

在服务器上执行：
```bash
curl "http://127.0.0.1:8001/ask?query=系统中的中药有哪些？"
```

若返回 JSON 结果，则说明后端启动成功 ✅

---

## ✅ 部署完成

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端 React | 3000 | 用户访问界面 |
| 后端 FastAPI | 8001 | 智能问答接口 |
| Neo4j 控制台 | 7474 | 图数据库管理（可选） |

---

## 📄 维护建议
- 修改 `.env` 后需重启后端容器或进程；
- 建议使用 `tmux` 或 `nohup` 保持服务持续运行；
- 可在后期接入 Nginx 反向代理，统一端口并启用 HTTPS。
