# -*- coding: utf-8 -*-
"""
中医病例数据导入脚本
作用：批量从 json_data/ 文件夹读取 f*.json 文件并导入 Neo4j。
说明：
- 保持 Case / Diagnosis / ZhengXing / Prescription / Herb 结构与 app.py 的 /refresh_kg 一致。
- Prescription 的唯一键为 (case_id, idx)。
- Herb 关系属性保存于 r.dose / r.prep，不再写入 Herb 节点属性。
"""

import json, glob, os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# ======== 加载 .env ========
load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", "test12345"))

driver = GraphDatabase.driver(URI, auth=AUTH)

# ======== 执行函数 ========
def run(tx, q, p=None):
    tx.run(q, p or {})


with driver.session() as s:
    # ====== 唯一约束 ======
    s.execute_write(run, """
    CREATE CONSTRAINT case_id_unique IF NOT EXISTS
    FOR (c:Case) REQUIRE c.case_id IS UNIQUE
    """)
    s.execute_write(run, """
    CREATE CONSTRAINT diag_name_unique IF NOT EXISTS
    FOR (d:Diagnosis) REQUIRE d.name IS UNIQUE
    """)
    s.execute_write(run, """
    CREATE CONSTRAINT zhengxing_name_unique IF NOT EXISTS
    FOR (z:ZhengXing) REQUIRE z.name IS UNIQUE
    """)
    s.execute_write(run, """
    CREATE CONSTRAINT herb_name_unique IF NOT EXISTS
    FOR (h:Herb) REQUIRE h.name IS UNIQUE
    """)

    # ====== 导入 json_data/ 文件夹下的 JSON ======
    files = sorted(glob.glob(os.path.join("json_data", "f*.json")))
    print(f"🔍 找到 {len(files)} 个病例文件。")

    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            v = json.load(f)

        cid = v["case_id"]
        print(f"➡ 导入 {cid} ({os.path.basename(path)}) ...")

        # ---- Case 节点 ----
        s.execute_write(run, """
        MERGE (c:Case {case_id:$case_id})
        SET c.symptoms=$symptoms,
            c.tongue=$tongue,
            c.pulse=$pulse,
            c.original_text=$original_text
        """, {
            "case_id": cid,
            "symptoms": v.get("symptoms", []),
            "tongue": v.get("tongue", []),
            "pulse": v.get("pulse", []),
            "original_text": v.get("original_text")
        })

        # ---- Diagnosis 节点 & 关系 ----
        for dname in v.get("diagnosis", []):
            s.execute_write(run, """
            MERGE (d:Diagnosis {name:$dname})
            WITH d
            MATCH (c:Case {case_id:$cid})
            MERGE (c)-[:HAS_DIAGNOSIS]->(d)
            """, {"cid": cid, "dname": dname})

        # ---- ZhengXing 节点 & 关系 ----
        for zname in v.get("zhengxing", []):
            s.execute_write(run, """
            MERGE (z:ZhengXing {name:$zname})
            WITH z
            MATCH (c:Case {case_id:$cid})
            MERGE (c)-[:HAS_ZHENGXING]->(z)
            """, {"cid": cid, "zname": zname})

        # ---- Prescriptions & Herbs ----
        for i, p in enumerate(v.get("prescriptions", [])):
            s.execute_write(run, """
            MERGE (pr:Prescription {case_id:$cid, idx:$idx})
            SET pr.formula=coalesce($formula, "（未明示方名/加减方）"),
                pr.method=$method
            WITH pr
            MATCH (c:Case {case_id:$cid})
            MERGE (c)-[:HAS_PRESCRIPTION]->(pr)
            """, {
                "cid": cid,
                "idx": i,
                "formula": p.get("formula"),
                "method": p.get("method")
            })

            for h in p.get("herbs", []):
                s.execute_write(run, """
                MERGE (herb:Herb {name:$name})
                ON CREATE SET herb.first_seen = date()
                WITH herb
                MATCH (pr:Prescription {case_id:$cid, idx:$idx})
                MERGE (pr)-[r:CONTAINS_HERB]->(herb)
                SET r.dose=$dose, r.prep=$prep
                """, {
                    "name": h.get("name"),
                    "dose": h.get("dose"),
                    "prep": h.get("prep"),
                    "cid": cid,
                    "idx": i
                })

print("✅ 所有病例导入完成。")

# ====== 导入完成后，简单统计 ======
with driver.session() as s:
    print("\n📊 节点数量:")
    res = s.run("""
    RETURN
      count { MATCH (c:Case) } AS case_count,
      count { MATCH (d:Diagnosis) } AS diag_count,
      count { MATCH (z:ZhengXing) } AS zhengxing_count,
      count { MATCH (p:Prescription) } AS pres_count,
      count { MATCH (h:Herb) } AS herb_count
    """).single()
    print(f"  Case: {res['case_count']}")
    print(f"  Diagnosis: {res['diag_count']}")
    print(f"  ZhengXing: {res['zhengxing_count']}")
    print(f"  Prescription: {res['pres_count']}")
    print(f"  Herb: {res['herb_count']}")
