# real_issue_001：Click #3802 的真实 Bug 定位实验

实验日期：2026-10-23（Asia/Shanghai）。仅完成一个案例，不进行参数调优或筛选最佳运行。

**结论：文件级 Top-1 未命中、Top-3 命中，实际修复文件排名第 2；相关代码区域未定位到，根因未解释。主要失败原因是阅读窗口选择，次要问题是候选排序和通用词噪声。**

## 1. 真实问题与版本

| 项目 | 记录 |
| --- | --- |
| 上游项目 | [pallets/click](https://github.com/pallets/click) |
| 真实 Issue | [#3802：`KeyboardInterrupt` during `click.prompt()` can race](https://github.com/pallets/click/issues/3802) |
| Issue 创建时间 | 2026-08-28T16:16:08Z |
| 修复 PR | [#3818](https://github.com/pallets/click/pull/3818)，已合并，正文明确关联 #3802 |
| 修复提交 | [`00f257bb8e714064bea16425007543bbc0800445`](https://github.com/pallets/click/commit/00f257bb8e714064bea16425007543bbc0800445) |
| 修复前提交 | [`b47c0529e99129d4785fecc2cb39a8ec8b4aa5f8`](https://github.com/pallets/click/tree/b47c0529e99129d4785fecc2cb39a8ec8b4aa5f8)，修复合并提交的第一父提交 |
| Issue 报告环境 | Python 3.14、Click 8.4.2，Ubuntu 22.04 ARM CI 中观察到；本次分析的是固定修复前提交，不等同于 8.4.2 发布包 |
| CodeLens 发布基线 | [V4 提交 e9e45c6](https://github.com/eydhb/V4-Benchmarking-Real-World-Bugs-and-Improving-Fault-Localization-Quality/commit/e9e45c6856bde4c875818759392e3d28c4787e26)；各定位模块的实际 SHA-256 见 run.json |

问题现象：用户在 `click.prompt()` 中按 Ctrl-C，Click 开始处理 `Abort`；在输出终止提示的过程中，如果又收到 `KeyboardInterrupt`，可能出现未捕获 traceback，而不是正常退出。Issue 提供了经过 `core.py`、`utils.py`、`_compat.py` 的堆栈。

## 2. 输入和实验约束

- 使用 Issue **完整标题 + 正文**，未翻译、未补充修复提示、未输入 PR 正文或 diff。确切输入见 [issue.txt](real_issue_001/issue.txt)。
- 使用 `offline` 规则模式，LangGraph 1.2.16、Python 3.11.4、Windows。本机未配置模型服务，本实验不衡量大模型能力。
- 工具预算维持原实现：最多 28 步、最多读取 10 个文件，每次搜索最多 40 条；没有为了命中而修改关键词、排序或源码。
- 修复标签在定位结果生成后用于独立评分。记录工具返回值的包装器原样调用现有 Repository 和 `analyze`，不修改搜索返回值或排序。
- 通过 GitHub 固定 SHA 源码归档取得 **166 个文件**，逐一与 GitHub Git tree 的 blob SHA-1 校验一致；分析前后再次校验 SHA-256。该目录为无 `.git` 的源码快照，未伪称是本地检出的完整 Git 历史。
- CodeLens 文件过滤后可检索 147 个文件；其余由现有规则排除。完整清单见 [run.json](real_issue_001/run.json)。导入目录仅包含上游修复前源码，报告、修复信息和标签位于目录之外。

输入限制：此次读取的是 2026-10-23 获取的 Issue 正文快照，GitHub 显示其更新时间晚于修复时间；没有取得历史编辑版本，因此不能保证正文与最初发布时逐字一致。没有读取后续评论作为 Agent 输入。Issue 自带堆栈及文件名提示，这属于问题输入的一部分，不应把该案例描述为完全没有文件线索的定位。

## 3. Agent 实际输出

原始输出：[result.json](real_issue_001/result.json)。首轮用时 1156 ms，20 次工具调用（文件列表 1 次、搜索 9 次、读取 10 次）。耗时是本机单次观测值，不是性能基准。

| 排名 | 候选文件 | 输出证据行 | 分值 | 是否为实际修复文件 |
| --- | --- | --- | --- | --- |
| 1 | `src/click/_termui_impl.py` | 97–99 | 13 | 否 |
| 2 | `src/click/core.py` | 98–100 | 13 | 是 |
| 3 | `src/click/utils.py` | 11 | 10 | 否 |
| 4 | `src/click/termui.py` | 183–185 | 9 | 否 |
| 5 | `src/click/exceptions.py` | 35–68 | 8 | 否 |
| 6 | `src/click/_compat.py` | 10 | 7 | 否 |

行范围是报告的起止行，范围内的证据可能不连续；精确行文本以原始 JSON 为准。分值只用于启发式排序，不是置信概率。所有输出证据行均已逐行与修复前源码核对一致，**引用真实不等于引用相关**。

对 `core.py`，Agent 最终只引用：

```python
# 修复前 src/click/core.py:98–100

    raise RuntimeError(message)

```

这是 `_check_nested_chain()` 的第 99 行，处理嵌套 chain group 的非法配置，与本次中断处理问题无关。其候选理由只是通用的“命中关键词或关联符号，需要结合调用路径确认”。

## 4. 实际修复位置与评分标签

修复提交更改四个文件，完整路径和 diff 保存于 [fix.json](real_issue_001/fix.json)：

| 修复文件 | 标签处理 | 理由 |
| --- | --- | --- |
| `src/click/core.py` | 纳入 | 唯一修改的生产代码文件，修复 `Command.main()` 的中断处理 |
| `tests/test_abort_interrupt.py` | 排除 | 新增回归测试，修复前不存在；不是待定位的生产代码 |
| `docs/exceptions.md` | 排除 | 异常行为说明文档 |
| `CHANGES.md` | 排除 | 更新记录 |

修复前的关键区域是 [`Command.main()` 第 1549–1595 行](https://github.com/pallets/click/blob/b47c0529e99129d4785fecc2cb39a8ec8b4aa5f8/src/click/core.py#L1549-L1595)，尤其是 `except Abort` 分支的第 1591–1595 行：在输出 `Aborted!` 时发生第二次中断，已经不在能捕获该中断的相应 try 区域内。

修复将异常处理拆为收集报告函数和退出码，然后统一输出并退出，由最外层捕获迟到的中断，保留既定退出码；消息允许丢失。修复也新增 `_echo_aborted()` 辅助函数。diff 在文件第 99 行附近出现新增函数的上下文，**不能因此认定 Agent 引用原有第 99 行就定位正确**：Agent 指向的是未修改的 `_check_nested_chain()`，而非上述故障处理逻辑。

评分使用单个生产代码标签 `src/click/core.py`，见 [case.json](real_issue_001/case.json) 和 [evaluation.json](real_issue_001/evaluation.json)：

| 指标 | 结果 |
| --- | --- |
| Top-1 | false |
| Top-3 | true |
| first_relevant_rank | 2 |
| reciprocal_rank | 0.5 |
| file_recall | 1.0（命中 1 / 标签 1） |
| 相关函数/代码区域 | 人工判定未命中，输出 98–100 行不覆盖故障区域 |
| 根因理解 | 未体现第二次中断、异常捕获范围或退出码保留机制 |

这里只计算单案例指标，不报告总体准确率或数据集 MRR。

## 5. 失败原因：检索、排序和根因理解分别判断

### 主要问题：检索后的阅读窗口选择

证据可在 [tool-results.json](real_issue_001/tool-results.json) 和原始结果的 trace 中复核：

1. `KeyboardInterrupt` 搜索返回 17 条，未截断，已命中 `core.py:1563`。因此不是“整个检索阶段完全没找到真实修复文件或相关异常”。
2. 初始 8 个搜索词为 `KeyboardInterrupt`、`during`、`click`、`prompt`、`can`、`race`、`Bug`、`When`。自然语言通用词消耗了有限名额；多个搜索返回达到 40 条上限并截断。
3. `race` 是不区分大小写的子串搜索，意外命中 `core.py:21` 的 `from types import TracebackType`。该行号成为该文件所有搜索命中的最小值。
4. 现有 `decide()` 用最小命中行号选择唯一的 100 行窗口，所以只读取 `core.py:9–108`，而不是第 1563 行附近。
5. 之后新增 `ClickException` 搜索再次命中 `core.py:1566`，但该文件已经进入 reads，策略不会回头读取另一个窗口。
6. `_offline_report()` 又用一般性的 `raise` 信号选择了第 99 行证据，最终报告没有使用已检索到的相关异常位置。

归类：**代码检索/阅读阶段失败，具体是窗口选择和不再读取同一文件的策略**。异常关键词检索本身已经提供足够线索，结果却在“搜索 → 阅读 → 证据”链路丢失。

### 次要问题：候选排序

`_termui_impl.py` 与 `core.py` 都得到 13 分（匹配数量加分达到上限，再加 Python 文件分值）。最终同分按路径排序，因此 `_termui_impl.py` 排第 1，`core.py` 排第 2。当前分数未区分精确异常标识符与通用词贡献，也没有利用堆栈位置。

这解释了 Top-1 失败。但即使只交换前两名，错误的第 98–100 行引用仍会保留，不能解决代码区域定位失败。

### 根因理解不足

规则报告没有解释第二次 `KeyboardInterrupt` 为什么逃出异常处理范围。它的 summary 和待验证项还沿用了“本次 500”“接口路径、令牌状态”等登录样例措辞，与 CLI 中断问题不符。此处是报告模板的场景偏差，不是实测大模型推理失败。

报告中对真实根因的解释来自实验结束后对修复 diff 与源码的人工分析，不能归功于 Agent。

## 6. 可复现步骤

在项目 `outputs/issue-locator/` 下执行。使用 `.venv/Scripts/python`（Windows）或已激活项目环境的 `python`。全新目录需要先按项目 README 安装依赖。

```powershell
# 在全新复现实验目录中准备固定版本，禁用自动换行转换以匹配源码字节。
git -c core.autocrlf=false clone https://github.com/pallets/click.git data/real_issue_001/source
git -C data/real_issue_001/source config core.autocrlf false
git -C data/real_issue_001/source checkout --detach b47c0529e99129d4785fecc2cb39a8ec8b4aa5f8

# 原始 artifacts 保持不变，新输出写入 data 目录。
.venv/Scripts/python experiments/run_real_issue_001.py --repo data/real_issue_001/source --output-dir data/real_issue_001/replay
.venv/Scripts/python -m issue_locator.evaluate --result data/real_issue_001/replay/result.json --case experiments/real_issue_001/case.json --output data/real_issue_001/replay/evaluation.json
```

当前工作区已经准备了经 Git blob 校验的源码快照，可直接运行后两步；`replay` 已包含本次复核结果，重复运行时应换一个新的输出目录。脚本拒绝覆盖原始输出。

复现脚本在运行前后核对所有源码文件的指纹及目录内容，校验每条候选证据，并记录 Python、LangGraph、运行模式、模块指纹与初始关键词。原始报告不依赖绝对机器路径。

已进行一次同案例复核：第二次结果在去除 `elapsed_ms` 后与首轮完全相同。这是重复性检查，不是第二个案例，也没有从多次运行中挑选更好结果。

## 7. 交付清单与验证范围

- [issue.json](real_issue_001/issue.json)、[issue.txt](real_issue_001/issue.txt)：问题快照和确切 Agent 输入。
- [source-manifest.json](real_issue_001/source-manifest.json)：源码版本、归档指纹、166 个文件指纹与 Git blob 校验记录。
- [run.json](real_issue_001/run.json)：运行环境、参数、定位模块指纹、可检索文件列表与校验记录。
- [result.json](real_issue_001/result.json)、[tool-results.json](real_issue_001/tool-results.json)：原始定位输出与完整搜索/读取响应。
- [fix.json](real_issue_001/fix.json)、[case.json](real_issue_001/case.json)、[evaluation.json](real_issue_001/evaluation.json)：修复证据、标签和独立评分。
- [run_real_issue_001.py](run_real_issue_001.py)：不向 Agent 传入修复信息的复现入口。
- [validation.json](real_issue_001/validation.json)、[test-results.txt](real_issue_001/test-results.txt)：评分重算、输入指纹、模块未变更、复跑一致性和项目测试记录。

最终检查通过：评分重算与保存结果一致，评分输入指纹一致，定位模块自运行以来没有改动；CodeLens 全套测试 37 项中 36 项通过、1 项因 Windows 符号链接权限跳过，0 失败。

本实验只运行 CodeLens 读取源码与定位，**未运行上游程序或复现操作系统信号竞争，也未运行 Click 的上游回归测试**。修复有效性的依据是已合并的修复和 diff；这里的验收范围是定位及其可复现评测。

## 8. 下一项改进建议（本次未实现）

优先改进阅读窗口：针对异常名、堆栈函数等高特异性命中选择窗口，允许同一文件读取多个不重叠区域。用这个固定案例检查是否实际读到 `Command.main()`，再评价 Top-1 排序。另行移除通用报告中写死的 HTTP 500 措辞。

本次止于保存一个有证据的基线结果：**Top-3 文件命中不等于 Bug 已诊断，关键失败是相关搜索命中没有转化为相关源码证据。**
