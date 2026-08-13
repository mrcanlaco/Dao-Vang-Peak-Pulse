with open('frontend/src/components/MainWorkspace.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace(
    "{/* OI + Funding Sub Chart (only when data exists) */}",
    "{/* OI + Funding Sub Chart (only when data exists) */}\n                {showOiFunding && (() => {"
)
code = code.replace(
    "                })()}",
    "                })()} }"
)
with open('frontend/src/components/MainWorkspace.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
