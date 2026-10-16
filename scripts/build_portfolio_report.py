"""Build the historical V1 report; current research uses build_research_portfolio.py."""
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main():
    quality = read("reports/quality/evaluation.json")
    study = read("reports/study_report.json")
    nhanes = read("reports/nhanes/summary.json")
    validation = read("reports/validation.json")
    q = quality["overall"]
    c = nhanes["counts"]
    tests = validation["local_pytest"]["tests"]
    ci = validation["ci"]["url"]
    source = validation["validated_source_commit"]
    repo = "https://github.com/Xenoxym/behavioral-research-data-workbench"
    title = "Behavioral Research Data Workbench — 项目验收与求职应用报告"
    intro = "已完成一套本地研究数据工作台：用合成数据演示筛选、访视、质量核查和修订，用独立的真实 NHANES 案例展示健康问卷与生物测量数据处理。项目目标是补充研究助理、研究数据支持和数字健康研究岗位的可核实作品证据。"
    metrics = [
        ("合成研究流程", f"{study['screened']} 筛选 / {study['enrolled']} 入组", "全部为虚构记录；不能表述为实际招募或管理参与者。"),
        ("纵向记录", f"{study['table_rows']['visits']} 访视 / {study['table_rows']['ema']:,} EMA", "访视状态、测量完整性与结局有效性分别解释。"),
        ("质量基准", f"TP {q['tp']} / FP {q['fp']} / FN {q['fn']}", f"{len(quality['per_rule'])} 类预设规则的问题匹配；干净数据 {quality['clean_findings']} 报警。"),
        ("真实公开数据", f"{c['analyzed_sample']:,} 名成人配对样本", "3 张 CDC 数据表；横断面、无权重的样本描述。"),
        ("软件验收", f"{tests} 项测试通过", "真实 Chromium 浏览器覆盖 7 页、下载与持久化修订；Windows/Ubuntu CI 通过。"),
    ]
    features = [
        ("标准化研究记录", "5 张关联表和 44 字段字典，说明类型、范围、单位与缺失编码；包含明确的模拟研究方案。"),
        ("质量核查", "重复 ID/事件、漏填、异常值、日期和跨表矛盾；硬错误与上下文核查提示分开，原始回答不被自动覆盖。"),
        ("随访管理", "按观察日期计算待完成、逾期、完成和退出；拒绝重复事件造成的歧义分母，屏蔽未来完成和退出信息。"),
        ("修订与追溯", "SQLite 保留原始快照、工作记录和追加式审计；修订必须有人员、原因、前后值与 UTC 时间；重复导入不抹除修订。"),
        ("真实健康数据", "下载 CDC XPT、校验 SHA256、验证一对一连接、保留拒答/不知道/跳题与检测限标志，生成样本流程和描述性报告。"),
        ("研究沟通", "一页研究报告、CSV/ZIP 导出、方法与局限说明、可复现命令和浏览器演示。"),
    ]
    fit = [
        ("HPRC Staff Research Assistant", "数据清理、记录准确性、随访组织、标准化流程、研究总结", "模拟流程不能替代真实参与者沟通或招聘要求的研究工作年限。"),
        ("Clinical Research Assistant / 初级数据协调支持", "访视窗口、缺失原因、数据问题、修订依据、数据库和报告", "没有实际 EDC 部署、IRB 研究实施或多用户权限经验的证据。"),
        ("Research Data / Public Health Analyst 初级方向", "pandas/SQL、健康数据连接、样本筛选、缺失与数据来源", "没有复杂抽样方差估计、因果推断或临床预测模型验证。"),
        ("Digital Health Research Support", "EMA 重复测量、上传与响应时间、纵向队列、可复现软件", "未部署真实手机研究平台，也未采集真实传感器数据。"),
    ]
    bullets = [
        "Built a Python/pandas, SQLite, and Streamlit workbench for synthetic behavioral-study screening, follow-up tracking, data-quality review, and reasoned corrections with preserved source records and audit history.",
        f"Defined a 44-variable data dictionary and evaluated field-level checks against {q['tp']} predefined defect matches across {len(quality['per_rule'])} rule categories; detected all labelled matches with {q['fp']} unexpected findings on the fixed synthetic benchmark.",
        f"Integrated three public CDC NHANES datasets into a reproducible descriptive analysis of {c['analyzed_sample']:,} paired adult records, handling questionnaire skip patterns, missing laboratory results, detection-limit flags, and source checksums.",
    ]
    technical = f"Implemented transactional correction history, canonicalized idempotent CSV imports, observation-date-aware visit denominators, and regression coverage verified by {tests} automated tests plus Windows/Ubuntu CI and a seven-page Chromium workflow."
    story = "I built this project to understand the data work behind a behavioral health study. The operational cohort is fully synthetic, so I could plant known defects and test whether checks found them without flagging legitimate skips or delayed uploads. I also analyzed public NHANES questionnaire and serum-cotinine data as a separate cross-sectional case. The main design choices were to preserve raw records, require a reason for corrections, and make follow-up denominators and missingness explicit. This is a portfolio project; I have not represented it as participant recruitment or clinical-trial employment."
    lessons = [
        "给一个合法 EMA 时间戳加入微秒，最初会让推断式解析低估回答数；改为显式 ISO8601 解析，并加入反例测试。",
        "SQLite 的事务上下文不会自动关闭连接；补充 finally 关闭，验证 Windows 下数据库可以移动。",
        "重复访视会重复计入完成率；改为拒绝歧义事件。非法带时区日历值与未来退出状态也有独立回归测试。",
        "真实 XPT 读取遇到 pandas 的极小零值伪影；只规范化已知精确伪影，原始下载字节和哈希保持不变。",
    ]
    limitations = [
        "42/42 是固定、预先设计的合成问题匹配，不是 42 名独立错误参与者，也不是未见临床数据上的 100% 准确率。",
        f"演示随访完成率 {study['followup']['completion_rate']:.1%} 只描述生成的数据；不能声称改善了真实留存或戒烟效果。",
        f"NHANES 成人基数 {c['adult_demographic_records']:,}，缺失可替宁 {c['adult_cotinine_missing']:,}；配对样本存在选择限制。结果未使用调查权重，不能作为全国流行率。",
        "可替宁体现多来源尼古丁暴露；不一致不能直接解释为参与者不诚实，也不能据此判定临床戒烟成功。",
        "仓库目前为私有，投递者无法凭普通公开链接阅读；需要分享导出的报告/截图，或由所有者另行选择公开。",
        "尚无真实参与者互动、真实临床试验、REDCap 实操、IRB 批准或临床合规认证；本地单用户演示不用于保密研究数据。",
    ]
    demo = [
        "启动 start_workbench.cmd，打开 http://localhost:8501；Overview 展示样本和分母。",
        "Quality review → Injected-error benchmark，运行并解释 TP/FP/FN，说明合法缺失与异常的区别。",
        "Follow-up 调整观察日期，说明未到期、窗口内和逾期，以及退出如何影响分母。",
        "Corrections & audit 修改一条 baseline readiness，填写 reviewer/reason；重开页面核实前后值和审计。",
        "Public data 展示真实样本流程、来源哈希和局限；Reports 导出一页研究报告。",
    ]
    def md_table(headers, rows):
        return "| " + " | ".join(headers) + " |\n| " + " | ".join(["---"] * len(headers)) + " |\n" + "\n".join("| " + " | ".join(row) + " |" for row in rows)
    md = f"# {title}\n\n{intro}\n\n[GitHub repository]({repo}) · [Validated CI]({ci})\n\nValidated source: `{source}`. Final report generated from saved measured artifacts; local/user data remain outside Git.\n\n## 实际交付与验收\n\n" + md_table(["证据", "实际结果", "解释"], metrics)
    md += "\n\n## 功能与岗位相关性\n\n" + md_table(["交付", "具体内容"], features) + "\n\n" + md_table(["岗位方向", "可提供的项目证据", "仍需真实经历补充"], fit)
    md += "\n\n## 简历项目条目（英文，可按岗位选择前 2–3 条）\n\n**Behavioral Research Data Workbench | Independent Portfolio Project | Python, pandas, SQLite, Streamlit**\n\n" + "\n".join("- " + bullet for bullet in bullets)
    md += "\n\n数据/软件岗位可用的补充条目：\n\n- " + technical
    md += "\n\n## 简历中文说明\n\n搭建行为研究数据工作台，完成合成筛选/随访数据管理、44 字段字典、质量检查和可追溯修订；在固定合成基准中检出全部 42 个预设问题匹配，未产生额外报警；另整合 CDC NHANES 三张公开数据表，完成 8,324 名成人配对样本的描述性分析及来源记录。\n\n## 60 秒英文面试说明\n\n" + story
    md += "\n\n## 面试中值得解释的修复与取舍\n\n" + "\n".join("- " + item for item in lessons)
    md += "\n\n## 五分钟演示路线\n\n" + "\n".join(f"{i}. {item}" for i, item in enumerate(demo, 1))
    md += "\n\n## 表述边界与下一步\n\n" + "\n".join("- " + item for item in limitations)
    md += "\n\n## 可核查证据\n\n- [Quality metrics](quality/evaluation.json)\n- [Study report](study_report.html)\n- [NHANES report](nhanes/report.html)\n- [Source manifest](nhanes/provenance_manifest.json)\n- [Software acceptance](validation.json)\n- [Protocol](../docs/PROTOCOL.md)\n- [Dictionary](../docs/data_dictionary.csv)\n- [NHANES methods](../docs/NHANES_METHODS.md)\n\n岗位覆盖是基于职责相似性的判断，不代表招聘结果或工作经验认证。投递 HPRC 时，将此项目放在研究数据与流程能力的位置；已有研究支持、沟通、协作经历仍应单独列出。\n"
    legacy = ROOT / "reports" / "legacy"
    legacy.mkdir(exist_ok=True)
    (legacy / "FINAL_PROJECT_REPORT_V1.md").write_text(md, encoding="utf-8")
    def table(headers, rows):
        return "<div class='table-wrap'><table><thead><tr>" + "".join(f"<th>{escape(x)}</th>" for x in headers) + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>" for row in rows) + "</tbody></table></div>"
    def listing(items):
        return "<ul>" + "".join("<li>" + escape(item) + "</li>" for item in items) + "</ul>"
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><style>
*{{box-sizing:border-box}}body{{background:#edf3f5;color:#18384b;font:15px/1.75 'Segoe UI','Microsoft YaHei',sans-serif;margin:0}}main{{max-width:1080px;margin:30px auto;background:white;padding:44px 52px;border-top:8px solid #087f83}}h1{{font-size:32px;line-height:1.3}}h2{{font-size:22px;border-top:1px solid #dce5e9;padding-top:23px;margin-top:32px}}.kicker{{font-size:12px;letter-spacing:2px;color:#087f83;font-weight:700}}.intro{{color:#526b78}}.evidence{{background:#e9f6f4;padding:16px;border-left:4px solid #087f83}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #dce5e9}}th{{background:#eef5f7}}a{{color:#087f83}}li{{margin-bottom:10px}}blockquote{{margin:16px 0;padding:20px 25px;background:#f1f6f8;border-left:4px solid #6da1ae}}code{{word-break:break-all;font-size:12px}}.muted{{font-size:12px;color:#647c89}}.resume{{background:#f7fafb;border:1px solid #dbe6eb;padding:20px 24px}}@media(max-width:700px){{main{{margin:0;padding:24px}}.table-wrap{{overflow-x:auto}}h1{{font-size:26px}}}}@media print{{@page{{size:A4;margin:16mm}}body{{background:white;font-size:11px}}main{{margin:0;padding:0;max-width:none}}h1{{font-size:25px}}h2{{font-size:17px}}table{{font-size:10px}}th,td{{padding:7px}}.resume,blockquote{{break-inside:avoid}}}}
</style></head><body><main><div class="kicker">COMPLETED PORTFOLIO / MEASURED EVIDENCE</div><h1>{escape(title)}</h1><p class="intro">{escape(intro)}</p><p><a href="{repo}">GitHub 仓库</a> · <a href="{ci}">已通过的 Windows / Ubuntu CI</a></p><p class="muted">Verified source: <code>{source}</code></p><div class="evidence">已完成可运行软件、合成问题基准、真实公开数据分析及求职表述。所有数值均取自保存的实际运行证据。</div>
<h2>实际交付与验收</h2>{table(['证据','实际结果','解释'],metrics)}<h2>功能与岗位相关性</h2>{table(['交付','具体内容'],features)}{table(['岗位方向','项目证据','仍需真实经历补充'],fit)}<h2>英文简历条目</h2><div class="resume"><strong>Behavioral Research Data Workbench | Independent Portfolio Project</strong><p>Python · pandas · SQLite · Streamlit</p>{listing(bullets)}</div><p>数据或软件岗位可选择：</p><blockquote>{escape(technical)}</blockquote><h2>中文项目说明</h2><p>搭建行为研究数据工作台，完成合成筛选/随访数据管理、44 字段字典、质量检查和可追溯修订；固定合成基准的 42 个预设问题匹配全部检出、无额外报警；另整合 CDC NHANES 三张公开数据表，完成 8,324 名成人配对样本的描述性分析。</p><h2>60 秒英文面试说明</h2><blockquote>{escape(story)}</blockquote><h2>值得解释的修复与取舍</h2>{listing(lessons)}<h2>五分钟演示路线</h2>{listing(demo)}<h2>表述边界与下一步</h2>{listing(limitations)}<h2>可核查证据</h2><p><a href="quality/evaluation.json">质量评估</a> · <a href="study_report.html">一页研究报告</a> · <a href="nhanes/report.html">真实数据报告</a> · <a href="nhanes/provenance_manifest.json">来源与哈希</a> · <a href="validation.json">软件验收</a> · <a href="../docs/PROTOCOL.md">研究方案</a></p><p class="muted">岗位覆盖基于职责相似性判断，不代表招聘结果或工作经历认证。研究支持、参与者沟通及协作经历应在简历中单独陈述。</p></main></body></html>"""
    (legacy / "FINAL_PROJECT_REPORT_V1.html").write_text(html, encoding="utf-8")
    print(str(legacy / "FINAL_PROJECT_REPORT_V1.html"))


if __name__ == "__main__":
    main()
