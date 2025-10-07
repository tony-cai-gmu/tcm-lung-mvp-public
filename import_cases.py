# -*- coding: utf-8 -*-
import json, glob, os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", "test12345"))

driver = GraphDatabase.driver(URI, auth=AUTH)

def run(tx, q, p=None):
    tx.run(q, p or {})

with driver.session() as s:
    # ====== 约束和索引 ======
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

        print(f"➡ 导入 {v['case_id']} ({path}) ...")

        # ---- Case 节点 ----
        s.execute_write(run, """
        MERGE (c:Case {case_id:$case_id})
        SET c.symptoms=$symptoms,
            c.tongue=$tongue,
            c.pulse=$pulse,
            c.original_text=$original_text
        """, {
            "case_id": v["case_id"],
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
            """, {"cid": v["case_id"], "dname": dname})

        # ---- ZhengXing 节点 & 关系 ----
        for zname in v.get("zhengxing", []):
            s.execute_write(run, """
            MERGE (z:ZhengXing {name:$zname})
            WITH z
            MATCH (c:Case {case_id:$cid})
            MERGE (c)-[:HAS_ZHENGXING]->(z)
            """, {"cid": v["case_id"], "zname": zname})

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
                "cid": v["case_id"],
                "idx": i,
                "formula": p.get("formula"),
                "method": p.get("method")
            })

            for h in p.get("herbs", []):
                s.execute_write(run, """
                MERGE (herb:Herb {name:$name})
                ON CREATE SET herb.first_seen = date()
                SET herb.last_dose=$dose, herb.prep=$prep
                WITH herb
                MATCH (pr:Prescription {case_id:$cid, idx:$idx})
                MERGE (pr)-[r:CONTAINS_HERB]->(herb)
                SET r.dose=$dose, r.prep=$prep
                """, {
                    "name": h.get("name"),
                    "dose": h.get("dose"),
                    "prep": h.get("prep"),
                    "cid": v["case_id"],
                    "idx": i
                })

print("✅ 所有病例导入完成。")

# ====== 导入完成后，做简单验证 ======
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
