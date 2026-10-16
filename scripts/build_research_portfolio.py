"""Build the current job-application report from completed real-data acceptance evidence."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import shutil

import pandas as pd

from study_workbench.research_reporting import REPORT_CSS, _md_table

ROOT = Path(__file__).resolve().parents[1]


def main():
    reports = ROOT / "reports"
    def read(name):
        return json.loads((reports / name).read_text(encoding="utf-8"))
    evidence = read("research_validation.json")
    manifest = read("research/source_manifest.json")
    stats = read("research/analysis_metadata.json")
    estimates = pd.read_csv(reports / "research/estimates.csv")
    overall = estimates.loc[estimates.group_variable.eq("overall")]
    total = int(overall.n.sum())
    tests = evidence["local_pytest"]["tests"]
    source = evidence["validated_source_commit"]
    repo = "https://github.com/Xenoxym/behavioral-research-data-workbench"
    title = "Tobacco Exposure Equity Study — 最终研究与求职报告"
    sections = []
    def add(heading, *paragraphs):
        sections.append((heading, list(paragraphs)))
    add("已完成的项目",
        f"已完成一项真实 CDC NHANES 数据的独立二次研究：收集并核对17个原始数据文件，覆盖3个不重叠调查时期，保留37,464条人口学记录构建抽样设计，主要分析纳入{total:,}条成人观察记录。当前默认页面、研究报告和结果表均以这项研究为主体。",
        "研究问题：收入较低人群的近期尼古丁暴露指标是否更高？家庭室内吸烟调整后，收入关联如何变化？问卷改版、检测限和缺失样本会怎样影响结果？研究计划先于比较性分析提交到 Git，再完整报告预设结果。",
        "原始问卷与生物测量由 CDC/NHANES 采集；本项目独立下载公开源文件、核对资料并开展二次分析。没有新招募参与者，也没有把模拟记录放入研究结果。")
    add("可以具体讨论的研究发现",
        "三期25岁以上主要样本的加权暴露率分别为19.6%（95%CI15.7–24.1）、18.1%（16.2–20.2）、13.7%（11.3–16.6）。低于贫困线组与达到贫困线4倍组的差距为22.5、26.8、27.6个百分点；跨时期差距变化的区间均包含零，因此不能宣称不平等显著扩大。",
        "检测限审计是有实质内容的方法学结果：最新一期用原生检测限得到47.5%的检出率，统一到0.015ng/mL则为36.7%，相差10.8个百分点。两者使用相同参与者，但定义不同；它们也不是主要0.05ng/mL暴露率。直接比较各期原生检出率会掩盖测量标准的变化。",
        "年龄范围同样影响叙事：18岁以上敏感性分析中，早期与最新一期收入差距的点估计为23.6与21.5个百分点。需要先说明目标人群，不能挑选支持某种趋势的年龄切点。",
        "9个预设模型均收敛。相同样本的 M1_common/M2 比较显示家庭室内吸烟调整后收入关联仍存在；不能据此估计因果中介比例。36项敏感性结果、24行缺失审计、全部模型项和置信区间均已保存。")
    add("这次实际做了哪些研究判断",
        "核查文献后把项目定位为重复验证与新数据扩展，而非声称发现收入不平等。将生物标志物、行为问卷、测量可比性和抽样统计连成完整证据链。",
        "发现最新 COT_L 文档要求的采血权重未出现在实际文件中；通过 HEPA_L 一对一恢复，并对 HEPB_S_L 独立文件逐项核对。未用普通体检权重替代，也未分析肝炎结局。",
        "核对电子烟题目拆分、CAPI到ACASI访谈变化、跳题与不知道/拒答编码。143名最新一期25岁以上受访者在三项旧式广义问题回答不用，却明确报告电子烟使用；这是问卷组合计数。进一步满足非当前卷烟、正权重和可替宁≤10条件者为24名，因此不能把143写成主要队列额外排除人数。",
        "完整抽样设计先于研究人群筛选；使用分层/聚类的 Taylor 方差、联合协方差的收入差值和匹配样本回归，区分缺少采血与采血后仍缺检验结果。所有核心数字来自可检查的传统统计计算。")
    fit = pd.DataFrame([
        ("HPRC / Behavioral Research Assistant", "健康行为文献、数据清理、标准化记录、质量核查、描述/分析报告", "实际参与者沟通、筛选入组和 IRB 执行需由真实工作补足"),
        ("Public Health / Research Data Analyst", "公开健康数据、复杂抽样、缺失与测量审计、R/Python、研究报告", "观察性结果没有因果识别，也未作政策效果评估"),
        ("Clinical Research Data Support", "字段字典、跨表一致性、可追溯流程、质量问题与报告", "没有实际 REDCap/EDC 部署或临床试验管理经验"),
        ("Digital Health / Biomedical Data Research", "生物标志物解释、行为信息整合、可复现软件和统计接口", "未开展医学影像、硬件采集、诊断模型或临床验证"),
    ], columns=["岗位方向", "作品提供的证据", "仍需诚实说明的边界"])
    english = [
        f"Conducted a reproducible NHANES secondary study of socioeconomic differences in nicotine exposure, harmonizing 17 CDC source files across three non-overlapping periods and analyzing {total:,} eligible adult observations.",
        "Estimated survey-weighted prevalence, income contrasts and adjusted associations using R survey; audited assay limits, questionnaire changes and laboratory nonresponse, reporting 36 prespecified sensitivity estimates and uncertainty.",
        f"Built a Python/Streamlit research interface with source checksums, exclusion flows and exportable reports; verified {tests} automated checks, real-browser workflows and byte-identical offline scientific replay.",
    ]
    add("可直接采用的英文简历条目", *english,
        "Suggested project title: Tobacco Exposure Equity Study | NHANES Secondary Research | Python, R survey, pandas, Streamlit | 2026.",
        "For a research-assistant application, prioritize the first two bullets. Keep SQLite/audit-trail engineering as a separately labeled legacy operations module only when space and job fit justify it.")
    add("中文版简历表述",
        f"基于17个 CDC NHANES 原始公开文件开展烟草暴露与收入差异的二次研究，完成三期变量协调、样本流程与质量审计，对{total:,}条符合预设条件的成人记录实施复杂抽样加权分析。",
        "使用 R survey 与 Python 估计暴露率、收入差值及调整后关联，完成36项敏感性分析，识别检测限变化对跨期比较的影响，并交付可复现代码、交互页面和研究报告。")
    add("面试时可以这样说明",
        "我选择了与癌症预防和健康行为相关的公开 NHANES 数据，先写下人群、暴露定义和敏感性方案，再分析收入差异。比较过程中，最关键的工作是发现最新血液文件缺少文档要求的权重，并用独立文件交叉核验；同时检查电子烟问题和检测限变化。结果支持收入差距持续存在，但不支持断言差距扩大。我把这些不确定性与数据来源一起保留在报告中。",
        "五分钟演示：先看真实研究总览与问题；进入收入分组和95%区间；对照敏感性页的原生/统一检测限；展示权重来源与样本流程；最后打开报告说明阴性结果和局限。",
        "应准备解释：为什么不能把普通体检权重用于最新采血结局；为什么先建完整抽样设计；为什么比较同一样本的模型；为什么相关性和 OR 变化不能证明因果或中介。")
    add("实际验收与复现",
        f"本地完整测试{tests}项通过，失败/错误/跳过均为0。独立统计校验以 R survey 内置参考数据和 Python 实现的 PSU-Taylor 协方差相互核对；参考数据与测试夹具从不进入研究发现。",
        "真实研究6页程序级检查通过；Chromium浏览器覆盖6页、分组选择、4项下载和报告内容。浏览器证据来自 GitHub CI；本机尝试曾因系统资源不足失败，未将其记成通过。",
        "完整离线复跑对5份科学结果CSV进行逐字节比较，输入与来源校验值一致、原始下载时间保持不变。远端还从官方来源重新下载并运行完整研究及离线复跑。",
        f"源代码验收提交：{source}。后续报告/截图提交仅补充证据。R运行时：{stats['r_version']}，survey {stats['package_versions']['survey']}。")
    add("范围、AI使用与局限",
        "AI参与问题讨论、资料核查和软件开发。研究数字均由公开源数据和确定性 Python/R 程序计算；没有让 LLM 生成测量值、填补参与者记录或决定结果。研究结论需要使用者理解并能解释。",
        "这是个人作品中的独立二次分析，尚未经同行评审。不能写成 NIH 试验工作经历、实际招募/随访人数、临床验证或真实患者管理。也不能用它替代职位要求的一年研究工作年限。",
        "已知收入梯度不是本项目首创。生物标志物有多种尼古丁来源，调查方式、选择与缺失可能影响比较；权重不能消除全部偏倚。没有宣称因果关系或精确复制 CDC 的30天禁烟判定。",
        "V1的合成筛选、访视、SQLite修订日志及42个缺陷匹配基准保留为历史模块，入口为 legacy_app.py；本次研究结果、默认页面和简历主条目均以真实研究为核心。")
    add("成果与证据链接",
        "Research report: reports/RESEARCH_REPORT.html / .md; source and analysis evidence: reports/research/; application evidence: reports/research_validation.json.",
        f"Repository: {repo}", f"Software CI: {evidence['ci']['url']}",
        f"Full real-data reproduction: {evidence['full_real_data_reproduction']['url']}",
        f"Source manifest: {len(manifest['sources'])} official files; {manifest['analytic_rows']:,} full demographic records; all acquisition/analysis code committed.")
    # Preserve the historical V1 report before replacing its user-facing entry point.
    legacy = reports / "legacy"
    legacy.mkdir(exist_ok=True)
    for suffix in ("html", "md"):
        path = reports / f"FINAL_PROJECT_REPORT.{suffix}"
        backup = legacy / f"FINAL_PROJECT_REPORT_V1.{suffix}"
        if path.exists() and not backup.exists():
            shutil.copyfile(path, backup)
    md = [f"# {title}"]
    html = ['<div class="eyebrow">COMPLETED REAL-DATA RESEARCH · CAREER EVIDENCE</div>', f"<h1>{escape(title)}</h1>"]
    for heading, paragraphs in sections:
        md += [f"## {heading}", *paragraphs]
        html += [f"<h2>{escape(heading)}</h2>", *(f"<p>{escape(p)}</p>" for p in paragraphs)]
        if heading == "这次实际做了哪些研究判断":
            md += ["## 岗位对应与经验边界", _md_table(fit)]
            html += ['<h2>岗位对应与经验边界</h2><div class="table">' + fit.to_html(index=False, escape=True, border=0) + '</div>']
    md += ["[完整研究报告](RESEARCH_REPORT.md)", "[方法与来源](research/source_manifest.json)", f"[GitHub]({repo})"]
    html += ['<p><a href="RESEARCH_REPORT.html">打开完整研究报告与图表</a> · <a href="research_validation.json">实际验收证据</a> · <a href="' + repo + '">GitHub</a></p>']
    (reports / "FINAL_PROJECT_REPORT.md").write_text("\n\n".join(md) + "\n", encoding="utf-8")
    (reports / "FINAL_PROJECT_REPORT.html").write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(title) + '</title><style>' + REPORT_CSS + '</style></head><body><main>' + ''.join(html) + '</main></body></html>', encoding="utf-8")
    print(f"Final real-data portfolio report built from validated source {source}")


if __name__ == "__main__":
    main()
