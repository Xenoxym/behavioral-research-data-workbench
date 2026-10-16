> Historical V1 synthetic demonstration. [Current real-data project report](../FINAL_PROJECT_REPORT.md).

# Behavioral Research Data Workbench — 项目验收与求职应用报告

已完成一套本地研究数据工作台：用合成数据演示筛选、访视、质量核查和修订，用独立的真实 NHANES 案例展示健康问卷与生物测量数据处理。项目目标是补充研究助理、研究数据支持和数字健康研究岗位的可核实作品证据。

[GitHub repository](https://github.com/Xenoxym/behavioral-research-data-workbench) · [Validated CI](https://github.com/Xenoxym/behavioral-research-data-workbench/actions/runs/38979236941)

Validated source: `ee50aa3b7c117c6d99acad992eec669e66e8e311`. Final report generated from saved measured artifacts; local/user data remain outside Git.

## 实际交付与验收

| 证据 | 实际结果 | 解释 |
| --- | --- | --- |
| 合成研究流程 | 240 筛选 / 182 入组 | 全部为虚构记录；不能表述为实际招募或管理参与者。 |
| 纵向记录 | 364 访视 / 2,409 EMA | 访视状态、测量完整性与结局有效性分别解释。 |
| 质量基准 | TP 42 / FP 0 / FN 0 | 23 类预设规则的问题匹配；干净数据 0 报警。 |
| 真实公开数据 | 8,324 名成人配对样本 | 3 张 CDC 数据表；横断面、无权重的样本描述。 |
| 软件验收 | 97 项测试通过 | 真实 Chromium 浏览器覆盖 7 页、下载与持久化修订；Windows/Ubuntu CI 通过。 |

## 功能与岗位相关性

| 交付 | 具体内容 |
| --- | --- |
| 标准化研究记录 | 5 张关联表和 44 字段字典，说明类型、范围、单位与缺失编码；包含明确的模拟研究方案。 |
| 质量核查 | 重复 ID/事件、漏填、异常值、日期和跨表矛盾；硬错误与上下文核查提示分开，原始回答不被自动覆盖。 |
| 随访管理 | 按观察日期计算待完成、逾期、完成和退出；拒绝重复事件造成的歧义分母，屏蔽未来完成和退出信息。 |
| 修订与追溯 | SQLite 保留原始快照、工作记录和追加式审计；修订必须有人员、原因、前后值与 UTC 时间；重复导入不抹除修订。 |
| 真实健康数据 | 下载 CDC XPT、校验 SHA256、验证一对一连接、保留拒答/不知道/跳题与检测限标志，生成样本流程和描述性报告。 |
| 研究沟通 | 一页研究报告、CSV/ZIP 导出、方法与局限说明、可复现命令和浏览器演示。 |

| 岗位方向 | 可提供的项目证据 | 仍需真实经历补充 |
| --- | --- | --- |
| HPRC Staff Research Assistant | 数据清理、记录准确性、随访组织、标准化流程、研究总结 | 模拟流程不能替代真实参与者沟通或招聘要求的研究工作年限。 |
| Clinical Research Assistant / 初级数据协调支持 | 访视窗口、缺失原因、数据问题、修订依据、数据库和报告 | 没有实际 EDC 部署、IRB 研究实施或多用户权限经验的证据。 |
| Research Data / Public Health Analyst 初级方向 | pandas/SQL、健康数据连接、样本筛选、缺失与数据来源 | 没有复杂抽样方差估计、因果推断或临床预测模型验证。 |
| Digital Health Research Support | EMA 重复测量、上传与响应时间、纵向队列、可复现软件 | 未部署真实手机研究平台，也未采集真实传感器数据。 |

## 简历项目条目（英文，可按岗位选择前 2–3 条）

**Behavioral Research Data Workbench | Independent Portfolio Project | Python, pandas, SQLite, Streamlit**

- Built a Python/pandas, SQLite, and Streamlit workbench for synthetic behavioral-study screening, follow-up tracking, data-quality review, and reasoned corrections with preserved source records and audit history.
- Defined a 44-variable data dictionary and evaluated field-level checks against 42 predefined defect matches across 23 rule categories; detected all labelled matches with 0 unexpected findings on the fixed synthetic benchmark.
- Integrated three public CDC NHANES datasets into a reproducible descriptive analysis of 8,324 paired adult records, handling questionnaire skip patterns, missing laboratory results, detection-limit flags, and source checksums.

数据/软件岗位可用的补充条目：

- Implemented transactional correction history, canonicalized idempotent CSV imports, observation-date-aware visit denominators, and regression coverage verified by 97 automated tests plus Windows/Ubuntu CI and a seven-page Chromium workflow.

## 简历中文说明

搭建行为研究数据工作台，完成合成筛选/随访数据管理、44 字段字典、质量检查和可追溯修订；在固定合成基准中检出全部 42 个预设问题匹配，未产生额外报警；另整合 CDC NHANES 三张公开数据表，完成 8,324 名成人配对样本的描述性分析及来源记录。

## 60 秒英文面试说明

I built this project to understand the data work behind a behavioral health study. The operational cohort is fully synthetic, so I could plant known defects and test whether checks found them without flagging legitimate skips or delayed uploads. I also analyzed public NHANES questionnaire and serum-cotinine data as a separate cross-sectional case. The main design choices were to preserve raw records, require a reason for corrections, and make follow-up denominators and missingness explicit. This is a portfolio project; I have not represented it as participant recruitment or clinical-trial employment.

## 面试中值得解释的修复与取舍

- 给一个合法 EMA 时间戳加入微秒，最初会让推断式解析低估回答数；改为显式 ISO8601 解析，并加入反例测试。
- SQLite 的事务上下文不会自动关闭连接；补充 finally 关闭，验证 Windows 下数据库可以移动。
- 重复访视会重复计入完成率；改为拒绝歧义事件。非法带时区日历值与未来退出状态也有独立回归测试。
- 真实 XPT 读取遇到 pandas 的极小零值伪影；只规范化已知精确伪影，原始下载字节和哈希保持不变。

## 五分钟演示路线

1. 启动 start_workbench.cmd，打开 http://localhost:8501；Overview 展示样本和分母。
2. Quality review → Injected-error benchmark，运行并解释 TP/FP/FN，说明合法缺失与异常的区别。
3. Follow-up 调整观察日期，说明未到期、窗口内和逾期，以及退出如何影响分母。
4. Corrections & audit 修改一条 baseline readiness，填写 reviewer/reason；重开页面核实前后值和审计。
5. Public data 展示真实样本流程、来源哈希和局限；Reports 导出一页研究报告。

## 表述边界与下一步

- 42/42 是固定、预先设计的合成问题匹配，不是 42 名独立错误参与者，也不是未见临床数据上的 100% 准确率。
- 演示随访完成率 84.9% 只描述生成的数据；不能声称改善了真实留存或戒烟效果。
- NHANES 成人基数 9,693，缺失可替宁 1,365；配对样本存在选择限制。结果未使用调查权重，不能作为全国流行率。
- 可替宁体现多来源尼古丁暴露；不一致不能直接解释为参与者不诚实，也不能据此判定临床戒烟成功。
- 仓库目前为私有，投递者无法凭普通公开链接阅读；需要分享导出的报告/截图，或由所有者另行选择公开。
- 尚无真实参与者互动、真实临床试验、REDCap 实操、IRB 批准或临床合规认证；本地单用户演示不用于保密研究数据。

## 可核查证据

- [Quality metrics](../quality/evaluation.json)
- [Study report](../study_report.html)
- [NHANES report](../nhanes/report.html)
- [Source manifest](../nhanes/provenance_manifest.json)
- [Software acceptance](../validation.json)
- [Protocol](../../docs/PROTOCOL.md)
- [Dictionary](../../docs/data_dictionary.csv)
- [NHANES methods](../../docs/NHANES_METHODS.md)

岗位覆盖是基于职责相似性的判断，不代表招聘结果或工作经验认证。投递 HPRC 时，将此项目放在研究数据与流程能力的位置；已有研究支持、沟通、协作经历仍应单独列出。
