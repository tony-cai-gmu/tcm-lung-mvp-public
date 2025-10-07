# -*- coding: utf-8 -*-
"""
LLM → Cypher → Neo4j（只读、安全、带 /schema、单轮会话上下文）
适配智谱 GLM API (默认: GLM-4.5-Air / 可切换 Flash)
"""

import os, re, json
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase

# ========== 环境 ==========
NEO4J_URI  = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "test12345")

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

GLM_API_KEY = os.getenv("GLM_API_KEY")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-4.5-air")  # 默认 Air，可切换为 Flash
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

client = None
llm_ready = False
if OpenAI and GLM_API_KEY:
    try:
        client = OpenAI(api_key=GLM_API_KEY, base_url=GLM_BASE_URL)
        llm_ready = True
        print(f"✅ 智谱 GLM 客户端就绪: 模型={GLM_MODEL}")
    except Exception as e:
        print(f"❌ GLM 初始化失败: {e}")
else:
    print("❌ GLM API Key 未设置或 openai 包未安装")

# ========== Neo4j 连接 ==========
neo4j_ready = False
try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as s:
        s.run("RETURN 1")
    neo4j_ready = True
    print(f"✅ Neo4j 连接成功: {NEO4J_URI}")
except Exception as e:
    print(f"❌ Neo4j 连接失败: {e}")

# ========== 上下文 ==========
LAST_CONTEXT: Dict[str, Dict[str, Any]] = {}

# ========== Graph Schema ==========
SCHEMA = {
    "nodes": {
        "Case": {"props": ["case_id", "symptoms[]", "tongue[]", "pulse[]", "zhengxing[]", "original_text"]},
        "Diagnosis": {"props": ["name"]},
        "Prescription": {"props": ["formula", "method", "case_id", "idx"]},
        "Herb": {"props": ["name"]},
        "ZhengXing": {"props": ["name"]}
    },
    "rels": [
        "(Case)-[:HAS_DIAGNOSIS]->(Diagnosis)",
        "(Case)-[:HAS_PRESCRIPTION]->(Prescription)",
        "(Case)-[:HAS_ZHENGXING]->(ZhengXing)",
        "(Prescription)-[r:CONTAINS_HERB {dose, prep}]->(Herb)"
    ]
}

# ========== FastAPI ==========
app = FastAPI(title="LLM → Cypher → Neo4j (GLM-4.5)", version="1.0.4")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CypherResponse(BaseModel):
    query: str
    cypher: str
    results: List[Dict[str, Any]] = []
    note: Optional[str] = None
    session_id: Optional[str] = None
    used_prev_context: bool = False
    answer: Optional[str] = None
    answer_format: Optional[str] = None

# ========== 安全检查 ==========
READ_ONLY_OK = re.compile(
    r"^\s*(CALL|MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN|WHERE|ORDER\s+BY|LIMIT|SKIP|PROFILE|EXPLAIN|UNION)\b",
    re.IGNORECASE
)
MUTATING_BAD = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH\s+DELETE|REMOVE|DROP|LOAD\s+CSV|APOC\.|CALL\s+dbms|CALL\s+db\.)\b",
    re.IGNORECASE
)

def is_safe_cypher(cypher: str) -> bool:
    if MUTATING_BAD.search(cypher):
        return False
    for line in [l.strip() for l in cypher.splitlines() if l.strip()]:
        if not READ_ONLY_OK.match(line):
            return False
    return True

def run_cypher(cypher: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    with driver.session() as s:
        return [dict(r) for r in s.run(cypher, params or {})]

# ========== Prompt ==========
def build_system_prompt(prev_ctx: Optional[Dict[str, Any]] = None) -> str:
    schema_lines = ["图模型："]
    for n, meta in SCHEMA["nodes"].items():
        schema_lines.append(f"- (:{n}) props={meta['props']}")
    schema_lines.append("关系：")
    for r in SCHEMA["rels"]:
        schema_lines.append(f"- {r}")
    schema_text = "\n".join(schema_lines)

    base = f"""你是一个“只生成 Neo4j Cypher 查询”的助手。所有答案必须来自数据库。
约束：
- Case.symptoms 是症状数组
- Case.tongue 是舌象数组
- Case.pulse 是脉象数组
- Prescription.method = 煎服方法
- (p)-[r:CONTAINS_HERB]->(h) 上存储剂量 dose 和 炮制方法 prep
- 查询时必须用 count(DISTINCT c) 按病例计数
- 返回字段命名用中文（症状, 舌象, 脉象, 证型, 疾病, 处方, 煎服方法, 炮制方法, 中药, 剂量, 频次, 案例号）
- 必须保证 RETURN 中用到的变量都在 MATCH 中定义过

{schema_text}
"""
    if prev_ctx:
        base += f"\n【上一轮上下文】：\n{json.dumps(prev_ctx, ensure_ascii=False)}\n"
    return base

def llm_to_cypher(nl_query: str, prev_ctx: Optional[Dict[str, Any]]) -> str:
    if not llm_ready:
        raise RuntimeError("GLM 未就绪")
    system = build_system_prompt(prev_ctx)
    user = f"当前用户问题：{nl_query}\n请直接给出唯一的可执行 Cypher。"
    resp = client.chat.completions.create(
        model=GLM_MODEL,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        temperature=0
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:cypher)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text

# ========== API 路由 ==========
@app.get("/", include_in_schema=False)
def root():
    return {
        "message": "这是后端 API 服务 (GLM-4.5, 支持 Air/Flash)",
        "endpoints": {
            "health": "/health",
            "model_info": "/model-info",
            "ask_example": "/ask?query=系统中都有哪些舌象？"
        }
    }

@app.get("/ask", response_model=CypherResponse)
def ask(query: str, session_id: str = "default", dryrun: bool = False):
    try:
        prev_ctx = LAST_CONTEXT.get(session_id)
        cypher = llm_to_cypher(query, prev_ctx)
        if not is_safe_cypher(cypher):
            raise HTTPException(status_code=400, detail=f"生成的 Cypher 非只读：\n{cypher}")
        if dryrun:
            return CypherResponse(query=query, cypher=cypher, results=[], note="dryrun=true")
        results = run_cypher(cypher)
        LAST_CONTEXT[session_id] = {"query": query, "cypher": cypher, "results": results}
        return CypherResponse(query=query, cypher=cypher, results=results,
                              session_id=session_id, used_prev_context=bool(prev_ctx))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败：{type(e).__name__}: {e}")

@app.get("/health")
def health():
    return {
        "status": "ok",
        "neo4j_ready": neo4j_ready,
        "neo4j_uri": NEO4J_URI,
        "llm_ready": llm_ready,
        "model": GLM_MODEL
    }

@app.get("/model-info")
def model_info():
    return {
        "llm_provider": "智谱 GLM",
        "current_model": GLM_MODEL,
        "switch_instruction": "export GLM_MODEL='glm-4.5-air' 或 'glm-4.5-flash'"
    }
