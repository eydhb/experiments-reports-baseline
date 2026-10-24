# 最小 Issue 定位评测器：使用与复现

本轮完成 3 个真实 Issue 的固定输出评测：Click #3802、#936、#1905。第一例复用此前完整保存的运行结果，后两例在各自修复前源码上运行了未修改定位策略的 CodeLens。全部使用 `offline` 规则模式；没有接入或评测真实模型。

## 交付物

- [reports/baseline.json](reports/baseline.json)：结构化总表，包含 Issue 编号、修复前/修复提交、候选文件排名、标签、逐例命中、汇总命中率、人工失败分析及输入指纹。
- [reports/baseline.md](reports/baseline.md)：由同一脚本自动生成的基线报告。
- [baseline_cases.json](baseline_cases.json)：参与评分的显式案例清单；不靠目录扫描隐式增减分母。
- [cases/](cases/)：3 份结构化案例定义，引用原始结果并固定结果 SHA-256。
- [../issue_locator/benchmark.py](../issue_locator/benchmark.py)：复用单例 evaluate 函数的批量评分入口，只依赖 Python 标准库。

## 一条命令重新评分

在 `outputs/issue-locator/` 目录运行：

```powershell
python -m issue_locator.benchmark --manifest experiments/baseline_cases.json --output experiments/reports/baseline.json
```

默认同时写出同名 `.md` 报告；可用 `--report` 指定 Markdown 路径。输出目录会自动创建。该操作不下载源码、不运行 Agent、不调用模型，也不需要 LangGraph 或 API 密钥。

验收重复性：

```powershell
python -m issue_locator.benchmark --manifest experiments/baseline_cases.json --output data/baseline-repeat.json
```

两个 JSON 与两个 Markdown 的字节内容应分别一致。输出不包含当前时间、运行耗时或机器绝对路径。已实际用 `python -S`（不加载 site-packages）运行两次，并核对字节一致；验证记录见 [reports/validation.json](reports/validation.json)。

## 案例与证据来源

| 案例 | 问题 | 已合并的修复 PR | 生产代码标签 |
| --- | --- | --- | --- |
| real_issue_001 | [Click #3802](https://github.com/pallets/click/issues/3802)：Ctrl-C 处理过程中再次中断 | [#3818](https://github.com/pallets/click/pull/3818) | `src/click/core.py` |
| real_issue_002 | [Click #936](https://github.com/pallets/click/issues/936)：短帮助文本默认宽度过小 | [#1002](https://github.com/pallets/click/pull/1002) | `click/core.py` |
| real_issue_003 | [Click #1905](https://github.com/pallets/click/issues/1905)：Windows 分页后删除临时文件失败 | [#2036](https://github.com/pallets/click/pull/2036) | `src/click/_termui_impl.py` |

每例在 `real_issue_00N/` 保存 issue.json、确切输入 issue.txt、source-manifest.json、fix.json、result.json、tool-results.json 和 run.json。修复前版本使用合并修复提交的第一父提交，分别为：

- #3802：`b47c0529e99129d4785fecc2cb39a8ec8b4aa5f8`。
- #936：`bd597172d7d6c7bd6d0a89ea89c0fd234452b290`。
- #1905：`09b9d614ac79e2c97f5f486a30231be1e8fe68ad`。

下载源码分别有 166、120、136 个文件，逐一与 GitHub Git tree 的 blob SHA-1 核对；运行前后校验全部文件的 SHA-256。定位仅输入标题、正文和修复前源码，修复 diff、标签和后续评论不传给 Agent。保存的每条候选证据都已逐行核对源码。定位阶段不执行被分析项目的代码。

标签使用修复中变化的生产代码文件。#3802 排除新增测试、文档和更新记录；#936 排除测试；#1905 修复只修改一个生产文件。具体排除理由在结构化案例的 `ground_truth_notes` 字段。#936 是帮助显示行为缺陷，不是崩溃；原始 Issue 可能讨论多种解决方案，此处只评价已合并 PR #1002 的生产文件改动。

## 统计口径与结果

按 Agent 原始顺序保留唯一文件，不以重复代码片段占用额外排名。Top-k 指前 k 个唯一候选中至少命中一个标签文件；汇总命中率是命中案例数 / 全部有效案例数。

当前结果：Top-1 = **0/3（0%）**，Top-3 = **1/3（33.33%）**。首个相关文件排名依次为 2、6、未命中。完整候选和逐例分析在自动生成报告中。

三个案例均暴露相关代码阅读不足：第一、二例已搜索到相关行，却读取文件头；第三例通用词搜索被文档截断，读取真实修复文件时仍停留在 import 区域。排序采用粗粒度分数与路径顺序，无法充分区分相关命中；`.rst` 文档也没有受到 `.md` 的同等降分。原规则报告的 HTTP 500 措辞不适用于这些问题。

这些分析是人工依据保存的工具响应和修复 diff 得到的，不由评分脚本自动推断。单个文件命中不代表函数、代码区域或根因定位成功。

## 数据验证与错误处理

- 支持从 1 个案例开始；真实清单包含 3 个案例。
- 每个案例必须有 GitHub Issue URL、与 URL 一致的编号、完整的修复前/修复 SHA、非空标签、结果路径和结果 SHA-256。
- 结果文件缺失、被修改、格式错误、重复案例/Issue、空清单或无效标签会导致整次评分非零退出；不会静默跳过从而缩小分母。
- 合法的空候选列表计为未命中，不当作运行失败或删除该案例。
- 未提供失败分析时，明确输出 `pending`；分析分类支持 `retrieval`、`ranking`、`root_cause`。
- JSON 和 Markdown 输出不得覆盖清单、案例定义或原始结果。
- 评分报告记录清单、案例和结果指纹。原始实验文件用 Git 属性保留字节，避免换行转换破坏已固定的指纹。

## 需要重新运行 Agent 时

重跑 Agent 和重新评分是两件独立操作。先在本地准备对应修复前版本，禁用换行转换：

```powershell
# 以 real_issue_002 为例；目录须尚不存在。
git -c core.autocrlf=false clone https://github.com/pallets/click.git data/real_issue_002/source
git -C data/real_issue_002/source config core.autocrlf false
git -C data/real_issue_002/source checkout --detach bd597172d7d6c7bd6d0a89ea89c0fd234452b290

# 使用已安装 LangGraph 的项目 Python；输出目录须为新目录。
python experiments/run_real_issue_001.py --repo data/real_issue_002/source --case-dir experiments/real_issue_002 --output-dir data/real_issue_002/replay
```

脚本名保留旧名称以兼容第一例；新增 `--case-dir` 后可验证并重放任意一份相同结构的固定案例。改进定位策略后应保存新的结果和新的案例清单，保留原始基线；不要覆盖原始输出再沿用旧指纹。

## 解释边界

本轮的“已测试”指运行 CodeLens 定位并核对源码证据，没有运行 Click 的应用或其历史回归测试来重新验证 Bug。Issue 正文来自当前可取的快照，未恢复历史编辑版本；部分输入自带堆栈或 API 名，这些线索会影响难度。只有 3 个同项目、人工选择的案例，不能推断跨项目准确率；也不是模型随机性评测。当前保证的是**对固定输入的评分可重复性**。
