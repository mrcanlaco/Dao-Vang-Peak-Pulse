with open('frontend/src/components/MainWorkspace.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

shap_start = code.find('{/* SHAP Risk Drivers Section — Enhanced */}')
if shap_start != -1:
    advanced_toggle = """
              <button 
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="w-full py-3 mt-4 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl text-sm font-bold text-slate-400 flex items-center justify-center gap-2 transition"
              >
                {showAdvanced ? <><ChevronUp className="w-4 h-4"/> Ẩn phân tích chuyên sâu</> : <><ChevronDown className="w-4 h-4"/> Hiển thị phân tích chuyên sâu (SHAP, Score Breakdown, Pump Pattern)</>}
              </button>

              {showAdvanced && (
                <div className="grid grid-cols-1 gap-3 mt-3">
"""
    code = code[:shap_start] + advanced_toggle + code[shap_start:]

    new_advanced_end = code.find('</>\n          ) : (')
    if new_advanced_end != -1:
        code = code[:new_advanced_end] + "                </div>\n              )}\n            " + code[new_advanced_end:]

        with open('frontend/src/components/MainWorkspace.tsx', 'w', encoding='utf-8') as f:
            f.write(code)
