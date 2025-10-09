import os
from docx import Document

input_folder = "raw_data"
output_folder = "raw_data_txt"
os.makedirs(output_folder, exist_ok=True)

for filename in os.listdir(input_folder):
    if filename.lower().endswith((".docx", ".doc")):
        input_path = os.path.join(input_folder, filename)
        output_path = os.path.join(output_folder, os.path.splitext(filename)[0] + ".txt")

        try:
            doc = Document(input_path)
            text = "\n".join([para.text for para in doc.paragraphs])
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"✅ Converted: {filename} -> {output_path}")
        except Exception as e:
            print(f"❌ Failed to convert {filename}: {e}")

print("🎯 All DOCX files converted to UTF-8 TXT successfully.")
