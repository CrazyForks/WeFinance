---
title: GOAI 2026 WeFinance 无界应用初赛材料 - Plan
type: feat
date: 2026-08-08
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
origin: hackathon/goai-2026-plan.md
execution: code
---

# GOAI 2026 WeFinance 无界应用初赛材料 - Plan

## Goal Capsule

- **Objective:** WeFinance 产出可提交 GOAI 2026 无界应用｜AI+金融赛道初赛材料的完整成果——事实核实过的作品简介、项目一页纸、PPT、数据合规说明、官方要求对照清单——外加两处必要代码改动（金融合规 prompt 修复、经营画像视图），在 8/16 23:59 前可提交。
- **Authority hierarchy:** GOAI 无界应用参赛手册 9.3/11 节红线 > `hackathon/goai-2026-plan.md` 既定决策 > 本计划。
- **Stop conditions:** 若浏览器实测发现线上 Demo 无法用真实凭据跑通 OCR/建议全链路，且用户短期内不能修复凭据，材料措辞必须如实改为"本地实测通过，线上部署中"，不得声称线上稳定运行。
- **Execution profile:** 单会话可执行，无需并行 worktree。
- **Tail ownership:** 完成后由用户负责登录 goaihz.com 提交材料、修改队名、核对报名信息。

---

## Product Contract

### Summary

WeFinance 需要在 8 天窗口（2026-08-08 至 8-16）内产出 GOAI 2026 无界应用赛道 AI+金融方向的初赛材料。项目现有 OCR、异常检测、可解释推荐能力契合赛题"资料理解、规则匹配、风险提示、投研整理"评审重点，但 `generate_detailed_report` 的提示词违反手册红线，且缺一个"新增贡献"的代码证据。

### Problem Frame

`hackathon/goai-2026-plan.md`（本计划 origin）已完成选型决策：对比 96 个 GitHub 仓库后选定 WeFinance 而非 MeetSpot，理由是 AI+金融赛题与现有 OCR+异常检测+可解释推荐技术栈直接复用。该文档列出 8 项"待 Claude Code 执行"任务，但两处风险未被覆盖：`services/recommendation_service.py:865` 的 `generate_detailed_report` 主动要求 LLM 给出确定性投资建议（违反手册 9.3/11 节红线）；线上 Demo 真实可用性未经验证（`curl` 返回 303，且同账号 MeetSpot 项目此前使用的 `newapi.deepwisdom.ai` 账号已被封禁）。

### Requirements

**赛道合规**

- R1. `generate_detailed_report` 的 prompt 不得要求 LLM 指名具体投资平台或给出确定性执行步骤（金额、时间表意义上的确定性操作指令），改为分析框架加自行核实口径。
- R2. 提交材料显式声明"原有基础（WeFinance 现有 OCR/分析/推荐/Agent 能力）加本次新增贡献"，不得让评审误认为是全新项目。

**产品证据**

- R3. 新增一个复用现有 `Transaction` 数据的"经营流水画像"聚合视图，作为 Agent 能力与任务闭环的代码证据，不引入新的收入/支出数据语义。
- R4. 材料中的"Demo 可运行"表述以浏览器实测为准，不凭历史文档描述断言。

**材料交付**（对应手册 5.2 初赛必交/可选材料）

- R5. 产出 500 字内作品简介，字段覆盖项目名称、所选行业赛题、问题与场景、核心解决方案、创新点、开放复用价值、当前进展。
- R6. 产出项目一页纸，覆盖手册附录 A 结构。
- R7. 产出 12 页方案 PPT（PPT/PDF），覆盖手册 5.2 场景来源、用户痛点、核心流程、产品形态、Agent 能力、工具数据模型使用方式、合规边界、后续落地计划。
- R8. 产出数据合规说明，覆盖数据类型、来源、授权方式、脱敏方式、第三方依赖披露。
- R9. 产出官方要求对照清单，逐条对照手册 5.2/8/9/10/11 节，如实标注状态，包括已知缺口（无 `tests/` 目录）。

### Scope Boundaries

- 本计划只覆盖初赛窗口（截至 8/16）交付。复赛（9/3 截止）要求的完整测试套件、正式代码仓库交付、Demo 视频剪辑不在本计划范围，留待复赛前单独计划。
- 不引入 `Transaction` 模型的收入/支出方向字段（模型级改动），经营画像视图只做既有数据的聚合视角切换。
- 不处理 Anna Builder Program 相关任务（`annaresearch.md` 记录的独立事项，origin 文档已明确不与本计划混淆）。

### Outstanding Questions

- 线上 Demo 实测结果未知，待 U1 执行确认。非阻塞——已在 Goal Capsule 的 stop condition 中处理为条件分支，不阻塞计划书写。

### Sources

- `hackathon/goai-2026-plan.md`（origin，完整决策记录）。
- `hackathon/goai-2026-manual.pdf`（GOAI 官方手册，20 页已读）。
- `~/vibecoding/MeetSpot/hackathon/goai-2026-submission/*`（同账号前序项目材料模板，只读参照，内容不复用）。
- `~/vibecoding/MeetSpot/hackathon/goai-2026-submission/项目体检与优化清单.md`（`newapi.deepwisdom.ai` 账号被封禁的第一手证据，触发 R4/U1）。
- `services/recommendation_service.py:865-1108`（`generate_detailed_report` prompt 现状，触发 R1）。
- `pages/investment_recs.py:336,346,467`（确认 `generate_detailed_report` 真实可达，非死代码）。

---

## Planning Contract

### Key Technical Decisions

- KTD1. **经营画像视图轻量复用，不建收入语义。** 新视图只按既有 `Transaction`（`amount` 恒为支出）做交易对手集中度、趋势、异常聚合，不新增收入字段。理由：8 天窗口内引入收入/支出方向是模型级改动，风险大于收益；手册评审重点是"资料理解/规则匹配"能力展示，不要求真实双向现金流建模。Alternative（引入收入方向字段建真实经营画像）已否决。
- KTD2. **合规修复只改 prompt 文本，不改函数签名。** `generate_detailed_report` 的调用方（`pages/investment_recs.py`）不变，只改内部 prompt 措辞。理由：改动面最小，降低回归风险，UI/交互不受影响。
- KTD3. **材料文件结构复用 MeetSpot 模板骨架，内容全部重写。** `hackathon/goai-2026-submission/` 目录结构和字段骨架参照 `~/vibecoding/MeetSpot/hackathon/goai-2026-submission/`，包括改写 `tools/build_goai_ppt.py` 生成 PPT。理由：该模板经过多轮打磨、字段结构对齐手册要求，复用结构不影响内容真实性，节省时间。

### Assumptions

- 若浏览器实测发现线上 API key 已失效，唤醒/修复凭据是用户侧任务，不在本计划的 Claude Code 执行范围，只需材料措辞如实反映。
- GOAI 报名账号已存在（origin 文档已确认），队名待用户自行修改。

### Sequencing

U1（浏览器实测）无阻塞，最先执行，其结果决定 U5/U6 材料里 Demo 相关措辞。U2（prompt 修复）与 U3（经营画像视图）互相独立，可并行构思但顺序实现。U4–U8（材料文件）依赖 U1–U3 的产出作为素材来源，最后执行。

---

## Implementation Units

### U1. 浏览器实测线上 Demo 真实状态

**Goal:** 确认 `wefinance-copilot.streamlit.app` 当前是否可用，走一遍真实上传到 OCR 到洞察到建议全链路，截图留证，为材料里的 Demo 措辞定调。
**Requirements:** R4
**Dependencies:** 无
**Files:** 无代码改动；产出截图素材至 `hackathon/goai-2026-submission/assets/`
**Approach:**
1. 用 Chrome MCP 打开 `https://wefinance-copilot.streamlit.app`
2. 若命中休眠页，点击公开可见的唤醒按钮，不触碰 Streamlit Cloud 账号或 Secrets 页面
3. 上传 `assets/sample_bills/` 内一张样例账单，走完 OCR、消费洞察、投资建议
4. 全流程截图，命名规范 `demo-{step}.png`

**Test scenarios:**
- Test expectation: none -- 纯验证性操作，无代码改动

**Verification:** 截图能看到真实结构化交易数据，不是空态或报错页；结果记录进 U8 官方要求对照清单的证据列。

---

### U2. 修复 `generate_detailed_report` 的确定性建议风险

**Goal:** 消除手册红线风险——不再要求 LLM 指名具体平台或给出确定性执行步骤。
**Requirements:** R1
**Dependencies:** 无
**Files:** `services/recommendation_service.py`（约 865-1108 行 `generate_detailed_report` 方法内的 prompt 字符串）
**Approach:**
1. 定位"开户与平台选择：推荐 3-5 个平台""自动化设置：详细的定投、止盈止损设置"等指令性措辞
2. 改写为分析框架加提示用户自行核实并咨询持牌机构的口径，保留原有报告结构（6 节）和字数区间要求
3. 不改函数签名，不改 `pages/investment_recs.py` 调用方代码

**Patterns to follow:** 现有 `_generate_llm_recommendations`（约 425-556 行）已经是更克制的写法（生成 2-3 条具体理财建议而非指名平台），可参照其措辞尺度。

**Test scenarios:**
- 用一条真实或样例交易数据触发 `generate_detailed_report`，人工检查输出不再包含具体平台名称或具体买入金额加时间表式的确定性指令
- Test expectation: 无自动化测试覆盖（仓库当前无 `tests/` 目录，见 R9 已知缺口），本单元验证方式为人工审阅 LLM 输出

**Verification:** 生成一次报告，输出仍是 4000-6000 字结构化建议，但读起来是分析加核实提示而非照做清单。

---

### U3. 新增经营流水画像聚合视图

**Goal:** 提供一个真实的、复用现有数据的新视图，作为 Agent 能力与任务闭环评审维度（25% 权重）的代码证据。
**Requirements:** R3
**Dependencies:** 无
**Files:** 新增 `pages/business_profile.py`（若探索后发现更适合扩展 `pages/spending_insights.py` 则改为该文件），复用 `modules/analysis.py` 现有聚合函数，复用 `utils/session.py::get_transactions`
**Approach:**
1. 读一遍 `pages/spending_insights.py` 全文和 `modules/analysis.py` 已有函数（如 `compute_anomaly_report`），确认可直接复用的聚合逻辑
2. 新视图按周期聚合：支出趋势（复用现有月度聚合）、交易对手集中度（按 merchant 分组排序，类比客户集中度）、异常预警（直接调用 `compute_anomaly_report`）
3. UI 沿用 `utils/ui_components.py` 现有卡片组件风格，不新建设计系统

**Patterns to follow:** `pages/spending_insights.py` 的页面结构（数据加载到聚合到图表渲染）。

**Test scenarios:**
- 上传样例账单后打开新视图，验证聚合数据来自真实 `Transaction`，不是占位符
- 无交易数据时的空态展示，不报错，给出引导文案
- Test expectation: 无自动化测试覆盖（同 R9 已知缺口），验证方式为本地 `streamlit run app.py` 手动走一遍

**Verification:** 新视图能渲染，展示的数字随上传账单变化，不是写死的样例数据。

---

### U4. 作品简介.txt

**Goal:** 500 字内，覆盖手册 5.2 必交字段。
**Requirements:** R5, R2
**Dependencies:** U2, U3
**Files:** 新增 `hackathon/goai-2026-submission/作品简介.txt`
**Approach:** 参照 `~/vibecoding/MeetSpot/hackathon/goai-2026-submission/作品简介.txt` 的 8 字段骨架（项目名称、所选行业赛题、问题与场景、核心解决方案、创新点与差异化、开放与复用价值、当前进展），内容完全基于 WeFinance 现状重写，"当前进展"段落须包含原有基础加本次新增贡献表述（R2）。

**Test scenarios:**
- Test expectation: none -- 纯文档产出

**Verification:** 字数不超过 500，8 字段齐全，不出现 MeetSpot 相关措辞。

---

### U5. 项目一页纸.md

**Goal:** 覆盖手册附录 A 结构。
**Requirements:** R6
**Dependencies:** U1, U2, U3
**Files:** 新增 `hackathon/goai-2026-submission/项目一页纸.md`
**Approach:** 参照 `~/vibecoding/MeetSpot/hackathon/goai-2026-submission/项目一页纸.md` 结构（基本信息、目标用户与核心问题、方案概述与核心流程、Agent 架构与关键能力、数据来源工具调用与技术路线、Demo 运行结果、安全合规边界、开放与复用贡献、后续计划与对接需求），Demo 运行结果段落直接引用 U1 的实测截图和数据。

**Test scenarios:**
- Test expectation: none -- 纯文档产出

**Verification:** 九个字段齐全，Demo 运行结果段落引用的是 U1 真实实测数据而非编造数字。

---

### U6. PPT 内容稿与生成的 pptx

**Goal:** 12 页方案 PPT。
**Requirements:** R7, R2
**Dependencies:** U1, U2, U3, U5
**Files:** 新增 `hackathon/goai-2026-submission/PPT-内容稿.md`；复制并改写 `~/vibecoding/MeetSpot/tools/build_goai_ppt.py` 为仓库内新建的 `tools/build_goai_ppt.py`（改 SLIDES 内容和配色为 WeFinance 品牌色）；运行生成 `hackathon/goai-2026-submission/WeFinance-GOAI2026-初赛PPT-v1.pptx`
**Approach:**
1. 先写 `PPT-内容稿.md`：封面、问题场景、方案总览、Agent 能力、技术与工程、Demo 演示（嵌 U1 截图）、数据与合规、AI+金融边界声明、开放复用、迭代计划、原有基础加本次新增贡献、结尾，共 12 页
2. 品牌色取自 `utils/design_system.py`，不用 MeetSpot 深蓝配色
3. 跑生成脚本产出 pptx，检查页数为 12

**Patterns to follow:** `~/vibecoding/MeetSpot/tools/build_goai_ppt.py` 的 python-pptx 结构（封面与正文两种 slide 模板、品牌条、图片嵌入逻辑）。

**Test scenarios:**
- Test expectation: none -- 纯文档产出

**Verification:** 生成的 pptx 能打开，12 页，Demo 页嵌入的是 U1 的真实截图而非占位图。

---

### U7. 数据合规说明.md

**Goal:** 覆盖手册 9.1 数据合规要求。
**Requirements:** R8
**Dependencies:** 无
**Files:** 新增 `hackathon/goai-2026-submission/数据合规说明.md`
**Approach:** 参照 `~/vibecoding/MeetSpot/hackathon/goai-2026-submission/数据合规说明.md` 五段结构（数据类型与来源、处理方式、授权与边界、第三方依赖披露、密钥管理），内容基于 WeFinance 实际架构：数据类型为账单图片、OCR 结构化数据、session 数据；处理方式引用 `utils/storage.py` 本地 JSON 持久化机制和无数据库事实；第三方依赖披露表列出 OpenAI 兼容 API（`OPENAI_BASE_URL` 可配置）；密钥管理引用 Streamlit Cloud Secrets 机制。

**Test scenarios:**
- Test expectation: none -- 纯文档产出

**Verification:** 五段齐全，如实反映 `utils/storage.py` 和 session state 的真实数据流，不编造合规声明。

---

### U8. 官方要求对照清单.md

**Goal:** 逐条对照手册要求，如实标注 WeFinance 当前状态。
**Requirements:** R9
**Dependencies:** U1, U2, U3, U4, U5, U6, U7
**Files:** 新增 `hackathon/goai-2026-submission/官方要求对照清单.md`
**Approach:** 参照 `~/vibecoding/MeetSpot/hackathon/goai-2026-submission/官方要求对照清单.md` 结构（初赛提交、复赛提交、评审权重、通用技术要求、附录 C 验证清单、红线自查），逐条填入 WeFinance 真实状态，显式标注两个已知缺口：`tests/` 目录不存在（复赛前需补，初赛不强制）、`generate_detailed_report` 生成耗时较长需注明性能预期。

**Test scenarios:**
- Test expectation: none -- 纯文档产出

**Verification:** 没有未知或空白状态遗留，两个已知缺口被显式标注而非隐瞒。

---

## Verification Contract

| 命令/动作 | 适用单元 | 说明 |
|---|---|---|
| `python -m py_compile services/recommendation_service.py pages/business_profile.py` | U2, U3 | 语法正确性检查 |
| `conda activate wefinance && streamlit run app.py --server.port 8501` | U2, U3 | 本地手动走一遍上传、分析、建议、经营画像视图 |
| Chrome MCP 打开线上 URL | U1 | 端到端真实性验证，产出材料所需截图 |
| 人工审阅 `generate_detailed_report` 输出文本 | U2 | 确认不再出现确定性平台或操作指令；无自动化测试覆盖，仓库当前无 `tests/`，已知缺口见 R9 |
| `black . && ruff check .` | U2, U3 | 代码格式与 lint |

---

## Definition of Done

- U1 完成，截图和真实性结论已写入 U5/U6 的 Demo 相关段落，不是编造数字
- U2 完成，`generate_detailed_report` 人工审阅确认不再违反手册 9.3/11 节红线
- U3 完成，新视图本地可运行且数据随真实上传变化
- U4-U8 全部产出，`hackathon/goai-2026-submission/` 目录下 6 个文件齐全，含生成的 pptx
- U8 官方要求对照清单没有空白或未知状态，两个已知缺口显式标注
- 清理：若 U3 探索后发现新增文件与既有 `pages/spending_insights.py` 功能重叠过多，需合并而非留两份相似代码
