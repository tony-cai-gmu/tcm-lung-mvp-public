# -*- coding: utf-8 -*-
"""
LLM → Cypher → Neo4j（只读、安全、带 /schema、单轮会话上下文）
完整的 Case–Diagnosis–ZhengXing–Prescription–Herb 路径闭环
"""

import os, re, json
from typing import Any, Dict, List, Optional, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase

# ========== 环境 ==========
NEO4J_URI  = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "test12345")

neo4j_ready = False
try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as s:
        s.run("RETURN 1")
    neo4j_ready = True
    print(f"✅ Neo4j 连接成功: {NEO4J_URI} 用户={NEO4J_USER}")
except Exception as e:
    print(f"❌ Neo4j 连接失败: {e}")

# OpenAI
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

client = None
llm_ready = False
if OpenAI and OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        llm_ready = True
        print(f"✅ OpenAI 客户端就绪: 模型={OPENAI_MODEL}")
    except Exception as e:
        print(f"❌ OpenAI 初始化失败: {e}")
else:
    print("❌ OpenAI API Key 未设置或 openai 包未安装")

# ========== 上下文 ==========
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

# ========== FastAPI ==========
app = FastAPI(title="LLM → Cypher → Neo4j (Read-Only, Single-Turn Context)", version="1.0.11")
'''
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
'''
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tcm-frontend.vercel.app",   # ✅ Vercel 前端
        "https://tcm-backend-nxdi.onrender.com",  # ✅ Render 自己
        "*"  # 临时开放测试
    ],
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

# ========== 校验 ==========
READ_ONLY_OK = re.compile(
    r"^\s*(CALL|MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN|WHERE|ORDER\s+BY|LIMIT|SKIP|PROFILE|EXPLAIN|UNION)\b",
    re.IGNORECASE
)
MUTATING_BAD = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH\s+DELETE|REMOVE|DROP|LOAD\s+CSV|APOC\.|CALL\s+dbms|CALL\s+db\.index\.|CALL\s+db\.)\b",
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

# ========== 格式化 ==========
def format_answer(query: str, results: List[Dict[str, Any]]) -> Tuple[str, str]:
    if not results:
        return f"没有找到符合条件的结果（问题：{query}）。", "list"
    if "频次" in results[0]:
        header = "| 项目 | 频次 |\n|------|------|"
        rows = [f"| {list(r.values())[0]} | {r['频次']} |" for r in results]
        return f"针对你的问题「{query}」，统计结果如下：\n\n{header}\n" + "\n".join(rows), "table"
    lines = [f"- {json.dumps(r, ensure_ascii=False)}" for r in results]
    return f"查询结果共 {len(results)} 条，详情如下：\n" + "\n".join(lines), "list"

# ========== 自动修正函数 ==========
def auto_fix_cypher(cql: str) -> str:
    """
    ✅ 最终稳定版：
    - 对 '证型为X的案例中' / '药方为X的案例中' 直接返回模板
    - 保留 UNWIND 修复逻辑
    - 所有模板都在 return fixed 之前执行
    """
    import re
    fixed = cql.strip()

    # === ① 修复 UNWIND ... WHERE ===
    def _fix_unwind_where(m):
        expr, var = m.group(1), m.group(2)
        with_prefix = "c, " if re.search(r"\(c\s*:\s*Case\)", fixed, flags=re.IGNORECASE) else ""
        return f"UNWIND {expr} AS {var} WITH {with_prefix}{var} WHERE "
    fixed = re.sub(
        r"UNWIND\s+([\w\.\[\]]+)\s+AS\s+(\w+)\s+WHERE\s+",
        _fix_unwind_where,
        fixed,
        flags=re.IGNORECASE
    )

    # === ② 特殊匹配：证型为 X 的案例中 ===
    m = re.search(r"证型为(.+?)的案例中", cql)
    if m:
        zname = m.group(1).strip().replace("'", "").replace("”", "").replace("“", "")
        # 判断问的是哪类对象
        if re.search(r"(药方|处方)", cql):
            return (
                f"MATCH (c:Case)-[:HAS_ZHENGXING]->(z:ZhengXing {{name:'{zname}'}}) "
                f"MATCH (c)-[:HAS_PRESCRIPTION]->(p:Prescription) "
                f"RETURN p.formula AS 处方, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
            )
        if re.search(r"中药", cql):
            return (
                f"MATCH (c:Case)-[:HAS_ZHENGXING]->(z:ZhengXing {{name:'{zname}'}}) "
                f"MATCH (c)-[:HAS_PRESCRIPTION]->(p:Prescription)-[:CONTAINS_HERB]->(h:Herb) "
                f"RETURN h.name AS 中药, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
            )

    # === ✅ 新增覆盖：药方为 X 的案例中 ===
    m = re.search(r"药方为(.+?)的案例中", cql)
    if m:
        formula = m.group(1).strip().replace("'", "").replace("”", "").replace("“", "")
        return (
            f"MATCH (c:Case)-[:HAS_PRESCRIPTION]->(p:Prescription {{formula:'{formula}'}}) "
            f"MATCH (c)-[:HAS_ZHENGXING]->(z:ZhengXing) "
            f"RETURN z.name AS 证型, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
        )

    # === ③ 兜底：去除多余换行、空格 ===
    fixed = re.sub(r"\s+", " ", fixed)
    return fixed



# ========== Prompt ==========
FOLLOWUP_HINTS = ("基于以上", "在此基础上", "继续", "接着", "刚才", "上一个", "上述", "前面的")

def build_system_prompt(prev_ctx: Optional[Dict[str, Any]] = None) -> str:
    schema_lines = ["图模型："]
    for n, meta in SCHEMA["nodes"].items():
        schema_lines.append(f"- (:{n}) props={meta['props']}")
    schema_lines.append("关系：")
    for r in SCHEMA["rels"]:
        schema_lines.append(f"- {r}")
    schema_text = "\n".join(schema_lines)
    examples = "\n".join([f"- {ex}" for ex in SCHEMA["examples"]])

    base = f"""你是一个“只生成 Neo4j Cypher 查询”的助手。所有答案必须来自数据库。

重要约束：
- Case.symptoms / Case.tongue / Case.pulse 均为数组，查询时需 UNWIND。
- 证型必须通过 (Case)-[:HAS_ZHENGXING]->(ZhengXing) 访问，不能从 Diagnosis 去连证型。
- Prescription.method = 煎服方法；CONTAINS_HERB.prep = 炮制方法；剂量(dose) 存在关系属性 r.dose。
- 统计频次时要用 count(DISTINCT c) 按病例计数。
- 查询“为空”时用 IS NULL / size(...)=0 或 NOT (c)-[:REL]->(:Node)。
- 返回字段命名必须中文（症状, 舌象, 脉象, 证型, 疾病, 处方, 煎服方法, 炮制方法, 中药, 剂量, 频次, 案例号, 原始文献）。

{schema_text}

示例：
{examples}
"""
    if prev_ctx:
        prev_json = json.dumps(prev_ctx, ensure_ascii=False)
        base += f"\n【上一轮上下文】：\n{prev_json}\n"
    return base

def llm_to_cypher(nl_query: str, prev_ctx: Optional[Dict[str, Any]]) -> str:
    if not client:
        raise RuntimeError("OpenAI 客户端未配置：请设置 OPENAI_API_KEY")
    system = build_system_prompt(prev_ctx)
    user = f"当前用户问题：{nl_query}\n请直接给出唯一的可执行 Cypher。"
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        temperature=0
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:cypher)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text

def looks_like_followup(q: str) -> bool:
    return any(q.strip().startswith(k) for k in FOLLOWUP_HINTS)

# ========== 路由 ==========
@app.get("/schema")
def schema():
    return {
        "policy": "answers_must_come_from_database_only",
        "neo4j": {"uri": NEO4J_URI},
        "schema": SCHEMA,
        "recommended_queries": RECOMMENDED_QUERIES
    }

@app.get("/ask", response_model=CypherResponse)
def ask(query: str, session_id: str = "default", dryrun: bool = False):
    try:
        prev_ctx = LAST_CONTEXT.get(session_id) if looks_like_followup(query) else None
        raw_cypher = llm_to_cypher(query, prev_ctx)
        import re
        cypher = None  # 初始化

        # ========== 模板1：证型为X → 药方 ==========
        if "证型为" in query and ("药方" in query or "处方" in query):
            m = re.search(r"证型为(.+?)的案例中", query)
            if m:
                zname = m.group(1).strip().replace("'", "")
                cypher = (
                    f"MATCH (c:Case)-[:HAS_ZHENGXING]->(z:ZhengXing {{name:'{zname}'}}) "
                    f"MATCH (c)-[:HAS_PRESCRIPTION]->(p:Prescription) "
                    f"RETURN p.formula AS 处方, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
                )

        # ========== 模板2：证型为X → 中药 ==========
        elif "证型为" in query and "中药" in query and "剂量" not in query and "炮制" not in query:
            m = re.search(r"证型为(.+?)的案例中", query)
            if m:
                zname = m.group(1).strip().replace("'", "")
                cypher = (
                    f"MATCH (c:Case)-[:HAS_ZHENGXING]->(z:ZhengXing {{name:'{zname}'}}) "
                    f"MATCH (c)-[:HAS_PRESCRIPTION]->(p:Prescription)-[:CONTAINS_HERB]->(h:Herb) "
                    f"RETURN h.name AS 中药, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
                )

        # ========== ✅ 模板8：证型为X → 使用中药Y的剂量与炮制方法 ==========
        elif "证型为" in query and "中药" in query and ("剂量" in query or "炮制" in query):
            m1 = re.search(r"证型为(.+?)的案例中", query)
            m2 = re.search(r"中药\s*([^\s,，。的]+)", query)
            if m1 and m2:
                zname = m1.group(1).strip().replace("'", "")
                hname = m2.group(1).strip()
                # 清理可能误匹配的词
                hname = re.sub(r"(的)?(剂量|炮制|方法|和|及).*", "", hname)
                cypher = (
                    f"MATCH (c:Case)-[:HAS_ZHENGXING]->(z:ZhengXing {{name:'{zname}'}}) "
                    f"MATCH (c)-[:HAS_PRESCRIPTION]->(p:Prescription)-[r:CONTAINS_HERB]->(h:Herb {{name:'{hname}'}}) "
                    f"RETURN DISTINCT h.name AS 中药, r.dose AS 剂量, r.prep AS 炮制方法"
                )

        # ========== 模板3：药方为X → 证型 ==========
        elif "药方为" in query and "证型" in query:
            m = re.search(r"药方为(.+?)的案例中", query)
            if m:
                formula = m.group(1).strip().replace("'", "")
                cypher = (
                    f"MATCH (c:Case)-[:HAS_PRESCRIPTION]->(p:Prescription {{formula:'{formula}'}}) "
                    f"MATCH (c)-[:HAS_ZHENGXING]->(z:ZhengXing) "
                    f"RETURN z.name AS 证型, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
                )

        # ========== 模板4：药方为X → 疾病 ==========
        elif "药方为" in query and ("疾病" in query or "病名" in query):
            m = re.search(r"药方为(.+?)的案例中", query)
            if m:
                formula = m.group(1).strip().replace("'", "")
                cypher = (
                    f"MATCH (c:Case)-[:HAS_PRESCRIPTION]->(p:Prescription {{formula:'{formula}'}}) "
                    f"MATCH (c)-[:HAS_DIAGNOSIS]->(d:Diagnosis) "
                    f"RETURN d.name AS 疾病, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
                )

        # ========== 模板5：药方为X → 中药 ==========
        elif "药方为" in query and ("中药" in query or "药物" in query):
            m = re.search(r"药方为(.+?)的案例中", query)
            if m:
                formula = m.group(1).strip().replace("'", "")
                cypher = (
                    f"MATCH (c:Case)-[:HAS_PRESCRIPTION]->(p:Prescription {{formula:'{formula}'}})-[:CONTAINS_HERB]->(h:Herb) "
                    f"RETURN h.name AS 中药, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
                )

        # ========== 模板6：疾病为X → 中药 ==========
        elif "疾病为" in query and "中药" in query:
            m = re.search(r"疾病为(.+?)的案例中", query)
            if m:
                dname = m.group(1).strip().replace("'", "")
                cypher = (
                    f"MATCH (c:Case)-[:HAS_DIAGNOSIS]->(d:Diagnosis {{name:'{dname}'}}) "
                    f"MATCH (c)-[:HAS_PRESCRIPTION]->(p:Prescription)-[:CONTAINS_HERB]->(h:Herb) "
                    f"RETURN h.name AS 中药, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
                )

        # ========== 模板7：疾病为X → 证型 ==========
        elif "疾病为" in query and "证型" in query:
            m = re.search(r"疾病为(.+?)的案例中", query)
            if m:
                dname = m.group(1).strip().replace("'", "")
                cypher = (
                    f"MATCH (c:Case)-[:HAS_DIAGNOSIS]->(d:Diagnosis {{name:'{dname}'}}) "
                    f"MATCH (c)-[:HAS_ZHENGXING]->(z:ZhengXing) "
                    f"RETURN z.name AS 证型, count(DISTINCT c) AS 频次 ORDER BY 频次 DESC"
                )

        # ========== 默认情况 ==========
        if cypher is None:
            cypher = auto_fix_cypher(raw_cypher)

        # 调试输出
        print("🧠 原始 LLM 输出:", raw_cypher)
        print("✅ 最终执行 Cypher:", cypher)

        # 安全检查
        if not is_safe_cypher(cypher):
            raise HTTPException(status_code=400, detail=f"生成的 Cypher 非只读或含有危险操作：\n{cypher}")

        if dryrun:
            return CypherResponse(query=query, cypher=cypher, results=[], note="dryrun=true")

        print("🚀 执行最终 Cypher:", cypher)
        results = run_cypher(cypher)

        LAST_CONTEXT[session_id] = {"query": query, "cypher": cypher, "results": results}
        answer_text, fmt = format_answer(query, results)

        return CypherResponse(
            query=query,
            cypher=cypher,
            results=results,
            session_id=session_id,
            used_prev_context=bool(prev_ctx),
            answer=answer_text,
            answer_format=fmt
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败：{type(e).__name__}: {e}")


@app.post("/reset")
def reset_session(session_id: str = "default"):
    LAST_CONTEXT.pop(session_id, None)
    return {"status": "ok", "message": f"session '{session_id}' 已清空"}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "neo4j_ready": neo4j_ready,
        "neo4j_uri": NEO4J_URI,
        "llm_ready": llm_ready,
        "model": OPENAI_MODEL
    }

@app.get("/", include_in_schema=False)
def root():
    return {
        "message": "LLM → Cypher → Neo4j API",
        "try": [
            "/health",
            "/schema",
            "/docs",
            "/ask?query=系统中都有哪些舌象？",
            "/ask?query=系统中都有哪些脉象？",
            "/ask?query=系统中有哪些处方的煎服方法及其频次？",
            "/ask?query=系统中有哪些中药的炮制方法及其频次？",
            "/ask?query=在中药为杏仁的案例中，都有哪些症状及其频次？",
            "/ask?query=在中药为白芍的案例中，都有哪些疾病及其频次？",
            "/ask?query=在中药为白芍的案例中，都有哪些证型及其频次？",
            "/ask?query=在单味药剂量为450g的案例中，都有哪些证型？",
            "/ask?query=列出系统中的所有原始文献",
            "/ask?query=列出系统中脉象为空的案例号",
            "/ask?query=列出系统中舌象为空的案例号",
            "/ask?query=列出系统中证型为空的案例号",
            "/ask?query=列出疾病名称为哮喘的证型及其频次"
        ]
    }


# =========================== ✅ 新增功能区 ===========================
import glob

# === JSON 文件在线编辑功能 ===
JSON_DIR = os.path.join(os.path.dirname(__file__), "json_data")

@app.get("/list_json_files")
def list_json_files():
    """列出 json_data/ 目录下的所有 JSON 文件"""
    try:
        files = [os.path.basename(f) for f in glob.glob(os.path.join(JSON_DIR, "*.json"))]
        return {"status": "ok", "files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取 JSON 文件列表失败：{e}")

@app.get("/get_json")
def get_json(filename: str):
    """读取指定 JSON 文件内容"""
    path = os.path.join(JSON_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{filename} 不存在")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取 {filename} 失败：{e}")

@app.put("/update_json")
def update_json(data: dict):
    """更新指定 JSON 文件（前端在线编辑保存）"""
    filename = data.get("filename")
    content = data.get("content")
    if not filename:
        raise HTTPException(status_code=400, detail="缺少 filename")
    path = os.path.join(JSON_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        return {"status": "ok", "message": f"{filename} 已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入 {filename} 失败：{e}")


# === 前端配置接口 ===
@app.get("/frontend_config")
def frontend_config():
    """提供前端可读的基础配置信息"""
    api_host = os.getenv("CODESPACE_NAME", "localhost")
    api_port = os.getenv("PORT", "8001")
    return {
        "api_base": f"http://{api_host}:{api_port}",
        "neo4j_uri": NEO4J_URI,
        "openai_model": OPENAI_MODEL,
        "llm_ready": llm_ready,
        "neo4j_ready": neo4j_ready,
    }


# === 前端自动检测更新接口（心跳式） ===
@app.get("/reload_frontend")
def reload_frontend():
    """
    提供给前端的轻量接口，用于检测后端是否更新。
    可让前端在热加载或版本更新时自动刷新界面。
    """
    import time
    return {
        "status": "ok",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "message": "Frontend reload check OK",
        "model": OPENAI_MODEL,
        "neo4j_ready": neo4j_ready
    }

# =========================== ✅ 新增功能区 ===========================
import glob

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
    """
    提供给前端的轻量接口，用于检测后端是否更新。
    可让前端在热加载或版本更新时自动刷新界面。
    """
    import time
    return {
        "status": "ok",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "message": "Frontend reload check OK",
        "model": OPENAI_MODEL,
        "neo4j_ready": neo4j_ready
    }



