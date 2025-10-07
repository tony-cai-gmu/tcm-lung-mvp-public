#!/bin/bash
set -e

# 配置
CONTAINER_NAME="tcm_neo4j"
NEO4J_USER="neo4j"
NEO4J_PASS="test12345"

echo "🚀 Step 1: 清空 Neo4j 数据库 (节点 + 关系 + 索引 + 约束)..."
docker exec -i $CONTAINER_NAME cypher-shell -u $NEO4J_USER -p $NEO4J_PASS "
DROP CONSTRAINT case_id_unique IF EXISTS;
DROP CONSTRAINT diag_name_unique IF EXISTS;
DROP CONSTRAINT zhengxing_name_unique IF EXISTS;
DROP CONSTRAINT herb_name_unique IF EXISTS;

DROP INDEX case_id IF EXISTS;
DROP INDEX diag_name IF EXISTS;
DROP INDEX zhengxing_name IF EXISTS;
DROP INDEX herb_name IF EXISTS;

MATCH (n) DETACH DELETE n;
"
echo "✅ 数据已清空"

echo "🚀 Step 2: 重新导入 f*** JSON 数据..."
python3 import_cases.py
echo "✅ 数据重新导入完成"

echo "🚀 Step 3: 验证节点数量..."
docker exec -i $CONTAINER_NAME cypher-shell -u $NEO4J_USER -p $NEO4J_PASS "
MATCH (c:Case) RETURN 'Case' AS label, count(c) AS count;
MATCH (d:Diagnosis) RETURN 'Diagnosis' AS label, count(d) AS count;
MATCH (z:ZhengXing) RETURN 'ZhengXing' AS label, count(z) AS count;
MATCH (p:Prescription) RETURN 'Prescription' AS label, count(p) AS count;
MATCH (h:Herb) RETURN 'Herb' AS label, count(h) AS count;
"
echo "✅ 验证完成"
