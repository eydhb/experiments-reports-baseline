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

分析状态：analyzed；分类：retrieval, ranking, root_cause。

搜索已命中 core.py:1563，但 race 子串误匹配 TracebackType，读取窗口变为 9–108 行；最终引用无关的 98–100 行。修复文件与首位候选同分，按路径排序列第 2；报告未解释第二次中断的捕获范围。

## real_issue_002

候选顺序：1. `click/__init__.py` → 2. `click/_bashcomplete.py` → 3. `click/_compat.py` → 4. `click/_termui_impl.py` → 5. `click/_unicodefun.py` → 6. `click/core.py`

真实修复文件：`click/core.py`

分析状态：analyzed；分类：retrieval, ranking, root_cause。

short 搜索已命中 core.py:771–773 的相关实现，但通用词和文件头部 import 命中使读取窗口停在 1–100 行，输出只引用 58–60 行。多个文件均为 13 分，路径排序使 core.py 排第 6；未解释默认短帮助宽度限制。

## real_issue_003

候选顺序：1. `CHANGES.rst` → 2. `CONTRIBUTING.rst` → 3. `docs/commands.rst` → 4. `docs/conf.py` → 5. `docs/options.rst` → 6. `docs/quickstart.rst`

真实修复文件：`src/click/_termui_impl.py`

分析状态：analyzed；分类：retrieval, ranking, root_cause。

前 8 个关键词未包含正文中的 _tempfilepager 或 unlink。多个通用词搜索被文档占据并截断；.rst 文档没有按 .md 的规则降分。直到第 10 次读文件才读到 _termui_impl.py:10–109 的文件头，未覆盖修复前 429–440 行；该文件未进入最终候选，未解释 mkstemp 文件描述符没有关闭。

## 解释边界

文件命中不代表代码区域或根因已定位。失败分析由人工填写，评分脚本不自动推断根因。
这是少量同项目案例的描述统计，不是跨项目准确率。版本、输入指纹及完整排名见同名 JSON。
