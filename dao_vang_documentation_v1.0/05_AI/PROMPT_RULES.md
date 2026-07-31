# PROMPT RULES

Prompt cho agent phải:

- nêu Task ID;
- dẫn Required Reading;
- nêu scope và allowed files;
- nêu acceptance;
- nêu tests/gate;
- nêu non-goals.

Agent phải:

- đọc source of truth;
- không đoán schema;
- không đổi label;
- không thêm feature ngoài spec;
- hỏi/dừng ở semantic boundary;
- báo residual risk.

Không dùng prompt kiểu “tự hoàn thiện mọi thứ” cho core research.
