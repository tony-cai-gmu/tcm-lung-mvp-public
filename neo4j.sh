#!/bin/bash
# 管理 Neo4j 容器的脚本（自动从 .env 读取账号/密码）

set -e

ENV_FILE="$(pwd)/.env"
CONTAINER_NAME="neo4j-lung"
IMAGE="neo4j:5.11"

# 读取 .env 文件里的环境变量
if [ -f "$ENV_FILE" ]; then
  export $(grep -v '^#' "$ENV_FILE" | xargs)
else
  echo "⚠️ 未找到 .env 文件，使用默认值"
fi

NEO4J_URI=${NEO4J_URI:-bolt://localhost:7687}
NEO4J_USER=${NEO4J_USER:-neo4j}
NEO4J_PASS=${NEO4J_PASS:-test12345}

case "$1" in
  start)
    echo "🚀 启动 Neo4j 容器：$CONTAINER_NAME"
    docker run -d \
      --name $CONTAINER_NAME \
      -p 7474:7474 -p 7687:7687 \
      -e NEO4J_AUTH="$NEO4J_USER/$NEO4J_PASS" \
      -v $(pwd)/neo4j_data:/data \
      $IMAGE
    ;;

  stop)
    echo "🛑 停止容器 $CONTAINER_NAME"
    docker stop $CONTAINER_NAME || true
    ;;

  restart)
    echo "🔄 重启容器 $CONTAINER_NAME"
    $0 stop
    docker rm -f $CONTAINER_NAME || true
    $0 start
    ;;

  status)
    docker ps --filter "name=$CONTAINER_NAME"
    ;;

  logs)
    docker logs -f $CONTAINER_NAME
    ;;

  *)
    echo "用法: bash neo4j.sh {start|stop|restart|status|logs}"
    exit 1
    ;;
esac
