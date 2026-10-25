# CodeLens 固定输出基线

案例数：3。仅评分已保存输出，无网络或模型调用。

Top-1：0/3（0.00%）；Top-3：1/3（33.33%）。

| 案例 | Issue | 修复前提交 | Top-1 | Top-3 | 首次命中排名 |
| --- | --- | --- | --- | --- | --- |
| real_issue_001 | [pallets/click #3802](https://github.com/pallets/click/issues/3802) | `b47c0529e99129d4785fecc2cb39a8ec8b4aa5f8` | False | True | 2 |
| real_issue_002 | [pallets/click #936](https://github.com/pallets/click/issues/936) | `bd597172d7d6c7bd6d0a89ea89c0fd234452b290` | False | False | 6 |
| real_issue_003 | [pallets/click #1905](https://github.com/pallets/click/issues/1905) | `09b9d614ac79e2c97f5f486a30231be1e8fe68ad` | False | False | None |

## real_issue_001

候选顺序：1. `src/click/_termui_impl.py` → 2. `src/click/core.py` → 3. `src/click/utils.py` → 4. `src/click/termui.py` → 5. `src/click/exceptions.py` → 6. `src/click/_compat.py`

真实修复文件：`src/click/core.py`

分析状态：pending；分类：待分析。

Pending manual analysis.

## real_issue_002

候选顺序：1. `click/__init__.py` → 2. `click/_bashcomplete.py` → 3. `click/_compat.py` → 4. `click/_termui_impl.py` → 5. `click/_unicodefun.py` → 6. `click/core.py`

真实修复文件：`click/core.py`

分析状态：pending；分类：待分析。

Pending manual analysis.

## real_issue_003

候选顺序：1. `CHANGES.rst` → 2. `CONTRIBUTING.rst` → 3. `docs/commands.rst` → 4. `docs/conf.py` → 5. `docs/options.rst` → 6. `docs/quickstart.rst`

真实修复文件：`src/click/_termui_impl.py`

分析状态：pending；分类：待分析。

Pending manual analysis.

## 解释边界

文件命中不代表代码区域或根因已定位。失败分析由人工填写，评分脚本不自动推断根因。
这是少量同项目案例的描述统计，不是跨项目准确率。版本、输入指纹及完整排名见同名 JSON。
