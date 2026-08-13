import re

with open('frontend/src/components/MainWorkspace.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

# Make sure all fragments are correct
# 1. 
# {showAdvanced ? <><ChevronUp className="w-4 h-4"/> Ẩn phân tích chuyên sâu</> : <><ChevronDown className="w-4 h-4"/> Hiển thị phân tích chuyên sâu (SHAP, Score Breakdown, Pump Pattern)</>}
code = code.replace("<><ChevronUp", "<React.Fragment><ChevronUp")
code = code.replace("chuyên sâu</>", "chuyên sâu</React.Fragment>")
code = code.replace("<><ChevronDown", "<React.Fragment><ChevronDown")
code = code.replace("Pattern)</>", "Pattern)</React.Fragment>")

# And the other ones...
# Wait, the error is 
# 194,6 JSX element 'div' has no corresponding closing tag.
# 546,15 Declaration or statement expected.
