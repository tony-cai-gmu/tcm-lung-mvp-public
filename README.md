# TCM-LUNG-MVP

MVP project for TCM Graph + FastAPI (Lung Cases)

## 📂 项目结构

tcm-lung-mvp/
│── app.py # FastAPI 后端主入口
│── requirements.txt # Python 依赖
│── .env.example # 环境变量示例文件
│── frontend/ # React 前端代码
│── README.md # 项目说明文档


---

## 🚀 环境准备

1. **安装 Python 依赖**
   ```bash
   pip install -r requirements.txt


2. **安装并运行 Neo4j**
赋予执行权限
chmod +x neo4j.sh
赋予执行权限
./neo4j.sh start
./neo4j.sh stop
./neo4j.sh start
./neo4j.sh status

3. **配置环境变量**

复制 .env.example 并改名为 .env，然后修改里面的内容：
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=test123
OPENAI_API_KEY=sk-xxxxxxx

