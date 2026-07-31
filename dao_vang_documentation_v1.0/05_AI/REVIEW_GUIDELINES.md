# REVIEW GUIDELINES

Integrator review theo thứ tự:

1. Scope đúng.
2. Diff không chạm file ngoài quyền sở hữu.
3. Semantic đúng specification.
4. Point-in-time và leakage.
5. Test coverage.
6. Error handling.
7. Reproducibility.
8. Dependency/complexity.
9. Documentation impact.
10. Gate result.

Reject nếu:

- future leakage;
- silent fallback;
- schema semantic đổi không version;
- test chỉ làm đẹp coverage;
- code ngoài scope;
- broad refactor không cần thiết.
