# CodeLens · Issue 定位评测基线

现已扩展为最小批量评测器：固定 3 个真实 Issue 的 Agent 输出，离线计算 Top-1 / Top-3。
当前 Top-1 为 0/3，Top-3 为 1/3；参见 [baseline.json](outputs/issue-locator/experiments/reports/baseline.json)、
[基线报告](outputs/issue-locator/experiments/reports/baseline.md) 和 [复现说明](outputs/issue-locator/experiments/BASELINE.md)。


本仓库保存 **Click #3802、#936、#1905** 三个真实 Issue 的定位实验，包含原始输出、源码版本证据、修复 diff、独立评分、复现脚本，以及运行所需的 CodeLens 源码和测试。首例另有完整人工报告：

- [实验报告：real_issue_001.md](outputs/issue-locator/experiments/real_issue_001.md)
- [原始定位输出](outputs/issue-locator/experiments/real_issue_001/result.json)
- [独立评分结果](outputs/issue-locator/experiments/real_issue_001/evaluation.json)
- [复现脚本](outputs/issue-locator/experiments/run_real_issue_001.py)

首例结果：**Top-1 未命中、Top-3 命中，实际修复文件排名第 2；代码区域和根因未正确定位。** 主要问题是阅读窗口选择，次要问题是候选排序。所有案例使用规则模式，不代表真实模型评测。

修复前版本为 `b47c0529e99129d4785fecc2cb39a8ec8b4aa5f8`，修复提交为 `00f257bb8e714064bea16425007543bbc0800445`。本仓库不包含下载的 Click 源码、虚拟环境或密钥；复现时按报告下载固定版本。保留原项目目录结构，报告中的相对链接和复现脚本可直接使用。

将 GitHub Issue 转换为有源码证据的候选文件，并用独立的文件级评测工具检查定位结果。

本阶段在初始 CodeLens 原型上加入可复现的评测入口，先完成[首例完整分析](outputs/issue-locator/experiments/real_issue_001.md)，再扩展到三例固定输出基线。**当前统计只描述这三个同项目案例，不代表跨项目准确率或真实模型效果。**

## 项目目标

项目围绕三个问题展开：

1. 如何根据问题描述，在仓库中找到值得检查的源码位置？
2. 如何让输出引用真实文件、真实行号和实际读取过的代码？
3. 如何对照实际修复文件，客观记录定位成功或失败？

定位与评分相互独立：Agent 只接收问题和待分析源码；修复文件标签在定位结果保存后由评测命令读取，避免将答案直接传入定位流程。

## 已实现功能

| 功能 | 说明 |
| --- | --- |
| 仓库导入 | 内置样例、本地源码目录、公开 GitHub 仓库 |
| 源码工具 | 文件枚举、字面量代码搜索、带真实行号的源码读取 |
| 定位编排 | LangGraph 调度搜索、读取与报告生成 |
| 规则模式 | 无需模型密钥，通过关键词和符号关联生成候选 |
| 模型模式 | 兼容 Chat Completions 的工具调用接口，可自主搜索和阅读 |
| 证据校验 | 过滤未读取的引用区间；检查读取后文件是否变化 |
| 结果导出 | 候选文件、依据、待验证项、工具轨迹和 JSON |
| 独立评分 | Top-1、Top-3、首个命中排名、倒数排名和文件召回率 |
| 可追溯报告 | 记录案例元数据、命中/遗漏文件及两个输入文件的 SHA-256 |

## 快速开始

需要 Python 3.11+。克隆本仓库需要 Git；应用内的 GitHub 导入也依赖 Git。

```powershell
git clone https://github.com/eydhb/experiments-reports-baseline.git
cd experiments-reports-baseline
cd outputs/issue-locator
.\start.ps1
```

也可双击 `outputs/issue-locator/start.bat`。首次启动会创建虚拟环境并安装依赖，需要网络。浏览器打开 http://127.0.0.1:8766/ ，使用内置问题“登录接口返回 500”开始定位。

手动安装并启动（适合其他平台）：

```bash
cd outputs/issue-locator
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m issue_locator.server --port 8766
```

`requirements.txt` 定义支持的依赖范围；`requirements-lock.txt` 保存原型验证时的精确版本，可用于兼容环境的版本复现。

## 运行定位与评分

以下命令均在 `outputs/issue-locator/` 中执行，定位命令使用已安装项目依赖的 Python。

```powershell
python -m issue_locator --repo ./sample_repo --issue "登录接口返回 500" --output experiments/sample-result.json
python -m issue_locator.evaluate --result experiments/sample-result.json --case experiments/sample_case.json --output experiments/sample-evaluation.json
```

评测模块只依赖 Python 标准库，不调用模型，不修改源码。输入是定位结果 JSON 和案例标签 JSON；输出目录需要已经存在，输出路径不能覆盖任一输入。

标签文件字段：

```json
{
  "case_id": "real_issue_001",
  "issue_url": "https://github.com/OWNER/REPO/issues/NUMBER",
  "base_commit": "填写修复前完整提交 SHA",
  "fix_commit": "填写真实修复提交 SHA",
  "expected_files": ["src/example.py"]
}
```

上述内容仅为格式示例，使用前需替换。标签中的版本信息由使用者提供，工具不会自行验证 Git 版本或修复提交。

### 评分口径

| 指标 | 含义 |
| --- | --- |
| `top_1_hit` | 排名第一的唯一文件是否属于标签文件 |
| `top_3_hit` | 前三个唯一文件中是否至少命中一个标签文件 |
| `first_relevant_rank` | 首个命中的排名，从 1 开始；未命中为 null |
| `reciprocal_rank` | 首个命中排名的倒数；未命中为 0 |
| `file_recall` | 全部候选命中的唯一标签文件数 / 唯一标签文件总数 |

同一文件的多个候选片段按首次出现去重，保留原始排序。路径大小写敏感，统一斜杠并去除 `./`，不按文件名模糊匹配。空候选计为未命中；空标签或非法路径拒绝评分。单个案例的倒数排名不等于数据集 MRR。

### 已保存的演示结果

[人工样例评分](outputs/issue-locator/experiments/sample-evaluation.json) 来自已有 `demo-result.json`：Top-1 未命中、Top-3 命中、首个命中排名为 3、倒数排名为 1/3、文件召回率为 1。

这只验证人工样例上的评分流程。`sample_case.json` 中的标签是人为指定的，没有对应真实 Issue 或修复提交，不能据此声称真实 Bug 定位成功。

## 如何开展第一个真实 Bug 实验

1. 选择具有明确修复提交的小型 Issue，记录完整 Issue URL、修复提交和修复前提交。
2. 在待分析仓库检出修复前版本，确认工作区干净；保存版本证据。
3. 使用修复前已有的问题描述，避免将透露修复位置的后续评论输入 Agent。
4. 运行定位并保存原始 JSON，记录模式、模型配置和实际问题文本。失败结果同样保留。
5. 独立审查修复 diff，确定 `expected_files`，记录排除测试、文档或格式改动的理由。重命名使用修复前路径，新建文件需说明不可定位性。
6. 执行评测命令，在 `experiments/real_issue_001.md` 中记录结果、证据和失败原因。
7. 分别检查文件命中、函数/代码区域和根因理解，基于失败证据选择下一项改进。

详细操作见 [评测流程](outputs/issue-locator/experiments/README.md)。已保存的 [real_issue_001](outputs/issue-locator/experiments/real_issue_001.md) 包含固定源码版本、原始定位输出、独立评分和失败原因分析。

## 可选模型配置

默认使用 `offline` 规则模式。模型模式需要支持工具调用的兼容服务；启动前在同一个 PowerShell 窗口设置：

```powershell
$env:LOCATOR_BASE_URL = 'https://你的模型服务地址/v1'
$env:LOCATOR_MODEL = '你的模型名称'
$env:LOCATOR_API_KEY = '你的密钥'
.\start.ps1
```

命令行选择 `--mode model`。模型模式会把问题、文件列表及必要源码片段发送到所配置的服务。密钥从环境读取，不应提交到仓库。模型协议和引用校验已有模拟测试，但未验证真实模型定位效果。

## 代码结构

```text
README.md
outputs/issue-locator/
  issue_locator/
    repository.py       # 文件枚举、搜索、读取与路径边界
    agent.py            # LangGraph 定位流程与证据校验
    model.py            # 模型工具调用客户端
    server.py           # 本地 HTTP 服务
    __main__.py         # 定位命令行入口
    evaluate.py         # 独立文件级评测入口
  web/                  # 中文工作台
  sample_repo/          # 人工 Java/Spring 风格静态样例
  tests/                # 工具、Agent、模型协议、HTTP、评测测试
  experiments/          # 评测说明、样例标签和评分报告
  demo-result.json      # 原型阶段保存的定位输出
  requirements.txt
  requirements-lock.txt
  start.ps1 / start.bat
```

## 测试与验证范围

```powershell
cd outputs/issue-locator
python -m unittest discover -s tests -v
# 只运行评测测试，无需安装 LangGraph：
python -m unittest discover -s tests -p test_evaluate.py -v
```

2026-10-24 在 Windows、Python 3.11、LangGraph 1.2.16 环境验证：**43 项测试，42 项通过，1 项因 Windows 符号链接权限跳过，0 失败**。单例与批量评分各有 6 项测试；批量评分无需安装 LangGraph，已验证重复生成报告字节一致。

覆盖路径越界与排除规则、真实行号、示例调用链、模型引用和文件变化、模型接口错误、HTTP 访问限制，以及评分边界、重复候选、非法输入、输入保护与报告指纹。历史 `test-results.txt`、`VALIDATION.md` 和界面测试记录来自初始原型，并非本轮新增的浏览器验证。

## 已知边界

- 规则模式不是大模型语义推理，也不是 AST 调用图分析。
- 内置 Java 样例是静态分析材料，不是可运行的登录应用。
- 候选位置和文件命中不代表已经确认故障根因；评分不会验证代码行或根因解释。
- 当前基线只覆盖 3 个同项目 Issue，更广泛的数据集和真实模型评测仍待完成。
- GitHub 导入当前面向公开仓库，默认浅克隆；真实实验建议手动准备固定版本的本地目录。
- 服务仅监听本机，不是公网多用户服务。仓库导入的限制和源码发送范围见应用说明。

## 来源与后续方向

本项目基于 [初始 CodeLens 原型](https://github.com/eydhb/issue-500-agent-makefile-src-controller) 的提交 `3eddd1f77132e9a0fad87defb908b4a6e588b96d`，本阶段增加独立评分模块、测试和实验流程文档。

下一步根据首个真实案例，优先改进源码阅读窗口选择，再用同一案例验证是否读到实际故障区域。暂不以增加新框架作为进度指标。

更多资料：[应用说明](outputs/issue-locator/README.md) · [示例定位报告](outputs/issue-locator/DEMO.md) · [评测流程](outputs/issue-locator/experiments/README.md) · [原型验证记录](outputs/issue-locator/VALIDATION.md)
