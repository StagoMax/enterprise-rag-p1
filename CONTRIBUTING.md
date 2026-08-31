# 贡献指南

感谢你改进 Enterprise RAG。这个仓库把可复现性、权限边界和证据链视为功能本身；任何质量结论都应能追溯到固定配置、Gold 版本和机器报告。

## 开发环境

需要 Python 3.12 与 [uv](https://docs.astral.sh/uv/)。基础开发和 CI 不需要 GPU、外部模型或 API 密钥。

```bash
git clone https://github.com/StagoMax/enterprise-rag-p1.git
cd enterprise-rag-p1
uv sync --extra dev
uv run ruff check .
uv run pytest -p no:cacheprovider
```

如需验证固定 Gold 的离线回归：

```bash
uv run python scripts/evaluate_p2.py \
  --backend hashing \
  --output reports/ci-hashing.json
uv run python scripts/compare_reports.py \
  reports/p2-baseline-hashing.json \
  reports/ci-hashing.json \
  --tolerance 0.02 \
  --ignore-thresholds
```

## 提交改动

1. 先确认问题的根因与所属边界，再选择检索、存储、路由、评测或界面中的正确模块。
2. 保持模块职责单一；共享需求应落在可复用抽象中，避免在不同检索路径重复修补。
3. 修复缺陷时补充最小回归测试；调整检索策略时同时保存配置、Gold SHA、候选规模和对比报告。
4. 不提交 `.env`、模型权重、本地数据库、私有语料或任何真实凭据。
5. 提交标题采用项目现有的 Conventional Commits 风格，例如 `feat(retrieval): ...`、`fix(sag): ...`、`docs: ...`。

## Pull Request 检查

- 说明问题、根因、方案和明确的非目标。
- 列出验证命令与结果；无法执行的检查需要说明原因。
- 指标变化必须在同一语料、Gold、分块契约、候选池和模型判断缓存下比较。
- 不把不同样本切片的分数串成同一条“提升曲线”。
- 涉及 ACL、租户或 Graph 扩展时，覆盖授权前置过滤与结果侧防御性复核。
- 涉及 UI 时附截图；涉及外部 API 时说明成本、缓存和失败策略。

安全问题请不要创建公开 Issue，按 [安全策略](SECURITY.md) 私下报告。
