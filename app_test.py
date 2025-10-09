# -*- coding: utf-8 -*-
"""
LLM → Cypher → Neo4j（安全、上下文支持、GraphRAG 问答）
✅ 恢复原版 Prompt（含强约束 + 示例）
✅ 保留 JSON 文件管理 / refresh_kg / 健康检查接口
✅ 修正 LLM 输出一致性（temperature=0）
"""

import os, re, json, glob
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase
from dotenv import load_dotenv
from pathlib import Path

# ========== 环境加载 ==========
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

NEO4J_URI  = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "test12345")

# ========== LLM 初始化 ==========
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

client, llm_ready = None, False
if OpenAI and OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        llm_ready = True
        print(f"✅ OpenAI 客户端就绪: 模型={OPENAI_MODEL}")
    except Exception as e:
        print(f"❌ OpenAI 初始化失败: {e}")
else:
    print("❌ OpenAI API Key 未设置或 openai 包未安装")

# ========== Neo4j 初始化 ==========
neo4j_ready = False
try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as s:
        s.run("RETURN 1")
    neo4j_ready = True
    print(f"✅ Neo4j 连接成功: {NEO4J_URI}")
except Exception as e:
    print(f"❌ Neo4j 连接失败: {e}")

# ========== FastAPI 应用 ==========
app = FastAPI(title="TCM GraphRAG 智能问答系统", version="3.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== Schema 与上下文 ==========
LAST_CONTEXT: Dict[str, Dict[str, Any]] = {}

# ========== Graph 模式 ==========
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
        "(Prescription)-[:CONTAINS_HERB {dose, prep}]->(Herb)"
    ],
    "examples": [
        # 症状
        "MATCH (c:Case) UNWIND c.symptoms AS s RETURN s AS 症状, count(*) AS 频次 ORDER BY 频次 DESC",

        # 舌象
        "MATCH (c:Case) UNWIND c.tongue AS t RETURN t AS 舌象, count(*) AS 频次 ORDER BY 频次 DESC",

        # 脉象
        "MATCH (c:Case) UNWIND c.pulse AS p RETURN p AS 脉象, count(*) AS 频次 ORDER BY 频次 DESC",

        # 证型
        "MATCH (c:Case)-[:HAS_ZHENGXING]->(z:ZhengXing) RETURN z.name AS 证型, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC",

        # 中药剂量&炮制方法
        "MATCH (p:Prescription)-[r:CONTAINS_HERB]->(h:Herb) RETURN h.name AS 中药, r.dose AS 剂量, r.prep AS 炮制方法 LIMIT 20",

        # 处方煎服方法
        "MATCH (p:Prescription) RETURN p.method AS 煎服方法, count(*) AS 频次 ORDER BY 频次 DESC",

        # 单味药剂量 → 证型
        "MATCH (c:Case)-[:HAS_ZHENGXING]->(z:ZhengXing), (c)-[:HAS_PRESCRIPTION]->(:Prescription)-[r:CONTAINS_HERB]->(:Herb) WHERE r.dose = '450g' RETURN DISTINCT z.name AS 证型",

        # 案例 → 处方 → 中药 → 症状
        "MATCH (c:Case)-[:HAS_PRESCRIPTION]->(p:Prescription)-[:CONTAINS_HERB]->(h:Herb {name:'杏仁'}) UNWIND c.symptoms AS s RETURN s AS 症状, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC",

        # 案例 → 处方 → 中药 → 疾病
        "MATCH (c:Case)-[:HAS_DIAGNOSIS]->(d:Diagnosis), (c)-[:HAS_PRESCRIPTION]->(:Prescription)-[:CONTAINS_HERB]->(h:Herb {name:'白芍'}) RETURN d.name AS 疾病, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC",

        # 案例 → 处方 → 中药 → 证型
        "MATCH (c:Case)-[:HAS_ZHENGXING]->(z:ZhengXing), (c)-[:HAS_PRESCRIPTION]->(:Prescription)-[:CONTAINS_HERB]->(h:Herb {name:'白芍'}) RETURN z.name AS 证型, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC",

        # ✅ 疾病 → 案例 → 证型（正确路径）
        "MATCH (c:Case)-[:HAS_DIAGNOSIS]->(d:Diagnosis {name:'哮喘'}), (c)-[:HAS_ZHENGXING]->(z:ZhengXing) RETURN z.name AS 证型, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC",

        # 疾病 + 案例号
        "MATCH (c:Case)-[:HAS_DIAGNOSIS]->(d:Diagnosis) RETURN d.name AS 疾病, c.case_id AS 案例号 ORDER BY 疾病, 案例号",

        # 原始文献
        "MATCH (c:Case) WHERE c.original_text IS NOT NULL RETURN c.case_id AS 案例号, c.original_text AS 原始文献 LIMIT 5",

        # 脉象为空
        "MATCH (c:Case) WHERE c.pulse IS NULL OR size(c.pulse)=0 RETURN c.case_id AS 案例号 ORDER BY c.case_id ASC",

        # 舌象为空
        "MATCH (c:Case) WHERE c.tongue IS NULL OR size(c.tongue)=0 RETURN c.case_id AS 案例号 ORDER BY c.case_id ASC",

        # 证型为空
        "MATCH (c:Case) WHERE c.zhengxing IS NULL OR size(c.zhengxing)=0 RETURN c.case_id AS 案例号 ORDER BY c.case_id ASC"
    ]
}

RECOMMENDED_QUERIES = [
    "系统中都有哪些症状及其出现频次？",
    "系统中都有哪些舌象？",
    "系统中都有哪些脉象？",
    "系统中都有哪些证型？",
    "系统中都有哪些疾病？",
    "系统中有哪些处方的煎服方法及其频次？",
    "系统中有哪些中药的炮制方法及其频次？",
    "在中药为杏仁的案例中，都有哪些症状及其频次？",
    "在中药为白芍的案例中，都有哪些处方及其频次？",
    "在中药为白芍的案例中，都有哪些疾病及其频次？",
    "在中药为白芍的案例中，都有哪些证型及其频次？",
    "在单味药剂量为450g的案例中，都有哪些证型？",
    "列出系统中的所有原始文献",
    "列出系统中脉象为空的案例号",
    "列出系统中舌象为空的案例号",
    "列出系统中证型为空的案例号"
]


# ========== Cypher 安全校验 ==========
READ_ONLY_OK = re.compile(
    r"^\s*(CALL|MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN|WHERE|ORDER\s+BY|LIMIT|SKIP|UNION)\b",
    re.IGNORECASE
)
MUTATING_BAD = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH\s+DELETE|REMOVE|DROP|APOC\.|CALL\s+db\.)\b",
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

# ========== Prompt 构建（恢复原版） ==========
def build_system_prompt(prev_ctx: Optional[Dict[str, Any]] = None) -> str:
    schema_lines = ["图模型结构如下："]
    for n, meta in SCHEMA["nodes"].items():
        schema_lines.append(f"- (:{n}) props={meta['props']}")
    schema_lines.append("关系：")
    for r in SCHEMA["rels"]:
        schema_lines.append(f"- {r}")
    schema_text = "\n".join(schema_lines)
    base = f"""你是一个专业的“Neo4j Cypher 查询生成助手”，任务是将自然语言问题转换为严格可执行的 Cypher 查询。
所有答案必须来自数据库，不能凭空编造。

约束：
- 所有 RETURN 中出现的变量必须在 MATCH 中定义
- 查询时必须使用 count(DISTINCT c) 按病例计数
- 查询症状、舌象、脉象字段时，必须使用 UNWIND 拆分数组
- 查询证型、疾病、方剂等频次时，必须通过 (c:Case) 变量来连接
- Prescription.method = 煎服方法
- (p)-[r:CONTAINS_HERB]->(h) 上存储剂量 dose 和 炮制方法 prep
- 字段命名统一为中文（症状, 舌象, 脉象, 证型, 疾病, 处方, 煎服方法, 炮制方法, 中药, 剂量, 案例号）

{schema_text}

示例：
问：系统中都有哪些症状？
→ MATCH (c:Case) UNWIND c.symptoms AS s RETURN s AS 症状, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC

问：各证型的病例数量？
→ MATCH (c:Case)-[:HAS_ZHENGXING]->(z:ZhengXing) RETURN z.name AS 证型, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC

问：含有中药杏仁的处方？
→ MATCH (p:Prescription)-[:CONTAINS_HERB]->(h:Herb {{name:'杏仁'}}) RETURN DISTINCT p.formula AS 处方名
"""
    if prev_ctx:
        base += f"\n【上一轮上下文】:\n{json.dumps(prev_ctx, ensure_ascii=False)}\n"
    return base

def llm_to_cypher(nl_query: str, prev_ctx: Optional[Dict[str, Any]]):
    if not llm_ready:
        raise RuntimeError("OpenAI 未就绪")
    system = build_system_prompt(prev_ctx)
    user = f"当前用户问题：{nl_query}\n请直接返回唯一可执行的 Cypher 查询（不要解释）。"
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0,
        timeout=30
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:cypher)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text

# ========== 结果格式化（恢复原版 format_answer） ==========
def format_answer(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "没有找到符合条件的结果。"
    keys = results[0].keys()
    table = "| " + " | ".join(keys) + " |\n| " + " | ".join(["---"]*len(keys)) + " |\n"
    for r in results:
        row = [str(r.get(k, "-")) for k in keys]
        table += "| " + " | ".join(row) + " |\n"
    return table

# ========== 主接口 /ask ==========
class CypherResponse(BaseModel):
    query: str
    cypher: str
    results: List[Dict[str, Any]] = []
    answer: Optional[str] = None
    note: Optional[str] = None
    session_id: Optional[str] = None
    used_prev_context: bool = False

@app.get("/ask", response_model=CypherResponse)
def ask(query: str, session_id: str = "default", dryrun: bool = False):
    try:
        prev_ctx = LAST_CONTEXT.get(session_id)
        cypher = llm_to_cypher(query, prev_ctx)
        if not is_safe_cypher(cypher):
            raise HTTPException(status_code=400, detail=f"生成的 Cypher 非只读：\n{cypher}")
        if dryrun:
            return CypherResponse(query=query, cypher=cypher, note="dryrun=true")
        results = run_cypher(cypher)
        answer = format_answer(results)
        LAST_CONTEXT[session_id] = {"query": query, "cypher": cypher, "results": results}
        return CypherResponse(query=query, cypher=cypher, results=results, answer=answer, session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败：{type(e).__name__}: {e}")

# ========== JSON 文件管理 ==========
JSON_DIR = os.path.join(os.path.dirname(__file__), "json_data")

@app.get("/list_json_files")
def list_json_files():
    return [os.path.basename(f) for f in glob.glob(os.path.join(JSON_DIR, "*.json"))]

@app.get("/get_json")
def get_json(filename: str):
    path = os.path.join(JSON_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{filename} 不存在")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.put("/update_json")
def update_json(data: dict):
    filename = data.get("filename")
    content = data.get("content")
    if not filename:
        raise HTTPException(status_code=400, detail="缺少 filename")
    path = os.path.join(JSON_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    return {"status": "ok", "message": f"{filename} 已更新"}

# ========== refresh_kg 单病例刷新 ==========
def run(tx, q, p=None): tx.run(q, p or {})

@app.post("/refresh_kg")
def refresh_kg(payload: dict):
    filename = payload.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="缺少 filename 参数")
    path = os.path.join(JSON_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"文件 {filename} 不存在")
    with open(path, "r", encoding="utf-8") as f:
        v = json.load(f)
    cid = v.get("case_id")
    if not cid:
        raise HTTPException(status_code=400, detail="JSON 文件缺少 case_id")

    with driver.session() as s:
        s.execute_write(run, "MATCH (c:Case {case_id:$cid}) DETACH DELETE c", {"cid": cid})
        s.execute_write(run, """
        MERGE (c:Case {case_id:$case_id})
        SET c.symptoms=$symptoms, c.tongue=$tongue, c.pulse=$pulse, c.original_text=$original_text
        """, {
            "case_id": cid,
            "symptoms": v.get("symptoms", []),
            "tongue": v.get("tongue", []),
            "pulse": v.get("pulse", []),
            "original_text": v.get("original_text")
        })
        for d in v.get("diagnosis", []):
            s.execute_write(run, "MERGE (d:Diagnosis {name:$d}) WITH d MATCH (c:Case {case_id:$cid}) MERGE (c)-[:HAS_DIAGNOSIS]->(d)", {"cid": cid, "d": d})
        for z in v.get("zhengxing", []):
            s.execute_write(run, "MERGE (z:ZhengXing {name:$z}) WITH z MATCH (c:Case {case_id:$cid}) MERGE (c)-[:HAS_ZHENGXING]->(z)", {"cid": cid, "z": z})
        for i, p in enumerate(v.get("prescriptions", [])):
            s.execute_write(run, """
            MERGE (pr:Prescription {case_id:$cid, idx:$idx})
            SET pr.formula=coalesce($formula, "（未明示方名/加减方）"), pr.method=$method
            WITH pr MATCH (c:Case {case_id:$cid})
            MERGE (c)-[:HAS_PRESCRIPTION]->(pr)
            """, {"cid": cid, "idx": i, "formula": p.get("formula"), "method": p.get("method")})
            for h in p.get("herbs", []):
                s.execute_write(run, """
                MERGE (herb:Herb {name:$name})
                ON CREATE SET herb.first_seen = date()
                WITH herb MATCH (pr:Prescription {case_id:$cid, idx:$idx})
                MERGE (pr)-[r:CONTAINS_HERB]->(herb)
                SET r.dose=$dose, r.prep=$prep
                """, {"name": h.get("name"), "dose": h.get("dose"), "prep": h.get("prep"), "cid": cid, "idx": i})
    return {"status": "ok", "message": f"✅ 病例 {cid} 已重新导入知识图谱"}

# ========== 健康检查 ==========
@app.get("/health")
def health():
    return {"status": "ok", "neo4j_ready": neo4j_ready, "llm_ready": llm_ready, "model": OPENAI_MODEL}

@app.on_event("shutdown")
def close_driver():
    driver.close()
