import os

filepath = "dao_vang_documentation_v1.0/01_Product/MVP_SCOPE.md"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Modify Top Trader Position Ratio line
content = content.replace(
    "Top Trader Position Ratio chưa nằm trong MVP v1, trừ khi ADR mới phê duyệt.",
    "Top Trader Position Ratio được tích hợp trong bản v1.1.0."
)

# Modify Out of scope section
content = content.replace("- real-time signals;", "~~- real-time signals;~~ (Moved to Post-MVP / v1.1 scope)")
content = content.replace("- dashboard production;", "~~- dashboard production;~~ (Moved to Post-MVP / v1.1 scope)")
content = content.replace("- Telegram/Discord alerts;", "~~- Telegram/Discord alerts;~~ (Moved to Post-MVP / v1.1 scope)")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
