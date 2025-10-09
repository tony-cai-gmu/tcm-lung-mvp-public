import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI

# ===== 1. 加载 .env 配置 =====
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not OPENAI_API_KEY:
    raise ValueError("❌ 未检测到 OPENAI_API_KEY，请在 .env 文件中添加。")

client = OpenAI(api_key=OPENAI_API_KEY)

# ===== 2. 路径设置 =====
INPUT_DIR = "raw_data_txt"
OUTPUT_DIR = "json_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== 3. 系统提示词 =====
SYSTEM_PROMPT = """
你是一名中医临床数据抽取助手，负责将中医病例文本转换为结构化 JSON，用于知识图谱建模。
请严格按照以下字段抽取，不要生成解释或多余文字，只输出 JSON。

字段定义如下（务必保持字段名一致）：
- diagnosis：疾病名称（如“咳嗽”“气喘”“胃脘痛”等）
- zhengxing：证型名称（如“表虚寒邪袭肺”“肝胃不和”等）
- symptoms：症状（主诉和现病史中的所有症状词，如“咳嗽”“气喘”“胃胀满”“盗汗”等）
- tongue：舌象描述（如“舌苔根稍腻”“舌淡红”等）
- pulse：脉象描述（如“脉细”“脉弦滑”等）
- formula：药方名称（如“玉屏风散”“黄芪桂枝汤加减”等）
- method：煎服方法或用药方法（如“每日一剂，分三次温服”“水煎服”等）
- herbs：一个数组，包含每味药的：
  - name：单味药名称（如“黄芪”“桂枝”）
  - dose：剂量（如“9g”“30克”等）
  - prep：炮制方法（如“炙”“炒”“生”，若无写明则为 null）
- comment：医家按语或病例总结。

请生成如下 JSON 结构：
{
  "case_id": "w001",
  "original_text": "...病例原文...",
  "diagnosis": [],
  "zhengxing": [],
  "symptoms": [],
  "tongue": [],
  "pulse": [],
  "prescriptions": [
    {
      "formula": "",
      "method": "",
      "herbs": [
        {"name": "", "dose": "", "prep": ""}
      ]
    }
  ],
  "comment": ""
}
注意：
1. 不要添加解释性文字；
2. 若无信息，请使用空数组或 null；
3. 每个病例仅输出一个 JSON。
"""


# ===== 4. 遍历病例文件 =====
for filename in sorted(os.listdir(INPUT_DIR)):
    if not filename.endswith(".txt"):
        continue

    case_id = os.path.splitext(filename)[0]  # e.g., w001
    input_path = os.path.join(INPUT_DIR, filename)
    output_path = os.path.join(OUTPUT_DIR, f"{case_id}.json")

    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    print(f"🩺 处理 {case_id} ...")

    # ===== 5. 调用 GPT 模型 =====
    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"病例号：{case_id}\n{text}"}
            ]
        )

        content = completion.choices[0].message.content.strip()

        # ===== 6. 提取 JSON 内容 =====
        match = re.search(r"\{[\s\S]+\}", content)
        if match:
            json_str = match.group(0)
            data = json.loads(json_str)
        else:
            data = {"error": "未检测到 JSON 输出", "raw_output": content}

        # ===== 7. 自动校验 & 补全 case_id =====
        if isinstance(data, dict):
            data["case_id"] = case_id
            if "original_text" not in data or not data["original_text"]:
                data["original_text"] = text

        # ===== 8. 保存结果 =====
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ 已保存 {output_path}")

    except Exception as e:
        print(f"❌ {case_id} 处理失败: {e}")

print("🎯 所有病例处理完成！")
