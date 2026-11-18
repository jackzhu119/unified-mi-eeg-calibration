# 输入空间协方差几何主导运动想象脑电的参数与目标函数自适应：跨三大校准范式的误差重分布与选择性控制研究

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Reproducibility: Verified](https://img.shields.io/badge/数据溯源-100%25_从三仓库锁定归档核验通过-success.svg)](#一键数据核验与出版级图表复现)
[![Regimes: I, II, III](https://img.shields.io/badge/三大校准范式-零样本跨被试_%7C_少标签跨会话_%7C_前序ERFC函数校准-6f42c1.svg)](#项目总览与三大范式核心科学发现)

**作者：** 朱子元 (Ziyuan Zhu)\*，刘思豪 (Sihao Liu)，余浩洋 (Haoyang Yu)  
**单位：** 重庆医科大学 人工智能医学学院（College of Artificial Intelligence Medicine, Chongqing Medical University），中国重庆 400016  
\*通信作者：朱子元（邮箱：`zzy2630816871@gmail.com`，ORCID：`0009-0005-1153-4926`）

> **[English README](README.md)** | **[英文旗舰主稿 PDF](manuscript/Unified_MIEEG_Manuscript_EN.pdf)** | **[英文主稿 Word](manuscript/Unified_MIEEG_Manuscript_EN.docx)** | **[中文对照主稿 Word](manuscript/Unified_MIEEG_Manuscript_ZH.docx)** | **[补充材料 PDF](manuscript/Supplementary_Materials_EN.pdf)**

---

## 项目总览与三大范式核心科学发现

本仓库将前期独立开展的三个运动想象脑电（MI-EEG）科研项目（累计覆盖 **88 个远程 Git 分支**、**6 个公开多被试/多会话 MI-EEG 数据集**、**>6,400 项已完成的 HPC 计算任务**）无损合并为一套**数学符号统一、评价算子贯通（试次级误差重分布四元组 $(C, I, D, G)$ 与动态弱势类召回率 $\text{Recall}_{\min}$）、可一键溯源核验的旗舰研究工程**：

1. **范式一（Regime I）：零样本跨被试迁移**（源自 [`jackzhu119/cross-subject-mi-eeg`](https://github.com/jackzhu119/cross-subject-mi-eeg)）：
   - **第一定律（多队列输入几何 vs. 风险目标函数不变性）**：单源队列分类器的严重弱势类崩塌（`Recall_min` 27.32%–35.71%）源于队列特异性的反方向决策边界偏置（BNCI 左偏 `79.29%/41.97%`，Yang 右偏 `49.94%/70.29%`）。在**严格固定 2,592 试次预算**下等比例混合双队列（`s60-matched`，90/90 项经典任务 100% 完成），正反偏置相互抵消，外部 Dreyer85（$n=85$）弱势类召回率跃升 **+11.00 pp**（`35.71%` $\to$ `46.71%`）、BA 提升 **+4.19 pp**（`60.63%` $\to$ `64.82%`），贡献了 12.8 倍全量数据增益（`s60-all`: `47.68%` `Recall_min`, `65.47%` BA）的 **>86%**；在深度网络 `BROAD` 上，`S60 vs S9` 将外部 `Recall_min` 提升 **+21.17 pp**（$p = 8.88 \times 10^{-17}$，72/85 人改善），并在 `S29` 处完全饱和（`S60 - S29` = **-0.55 pp**，$p_{\text{Holm}}=1.000$）。相反，在固定多队列源池上改用 5 种复杂风险目标函数（`paper1-risk-v1` 90/90 任务）至多仅带来 **+1.28 ~ +1.35 pp** 的非显著变化（$p \ge 0.124$），而盲目放大高噪声被试权重的 `GroupDRO` 在外部集上灾难性崩塌 **-8.75 pp**（$p_{\text{Holm}} = 4.0 \times 10^{-5}$）。

2. **范式二（Regime II）：少标签（$B=20$）纵向跨会话重校准**（源自 [`jackzhu119/few-shot-mi-eeg`](https://github.com/jackzhu119/few-shot-mi-eeg)）：
   - **第二定律（预滤波协方差白化打破误差抵消 & 时间窗-几何物理对应律）**：无对齐的监督空间重拟合（`Full CSP - LDA-only`）在外部 BNCI9 上完全停滞（**+0.19 pp**，$p_{\text{Holm}}=1.00$），原因是纠正错误（$C=4.17\text{ pp}$）与新引入错误（$I=3.98\text{ pp}$）发生 **97.73% 的相互抵消**。在滤波前引入仅依赖支持集无标签二阶统计量的欧氏白化（`EA - Full`），在 Kumar12（**+5.30 pp**，$C=14.61, I=9.32$）与 BNCI9（**+5.65 pp**，$C=12.78, I=7.13$，9/9 全员提升，$p_{\text{Holm}}=0.0117$）上同步实现正向净误差重分布，并将动态弱势类召回拉升 **+10.45 pp** 与 **+8.52 pp**。进一步通过 **544 次几何拆解拟合**与 **148 次时间窗相位拟合**证明：5s 宽提示窗（`[0, 5) s`）中的纵向漂移以非任务期全局幅值缩放（`Common RMS`）为主（裁剪至 2s 纯任务窗 `[2, 4) s` 后额外 EA 增益消失，配对差 **-7.73 pp**），而紧凑任务窗（BNCI9）中的漂移由非对角跨通道协方差旋转主导（`Full EA` 超越 `RMS` **+4.63 pp**）。

3. **范式三（Regime III）：小样本前序神经、流形与保留证据的函数式校准（ERFC）**（源自 [`jackzhu119/research3`](https://github.com/jackzhu119/research3) 第 1–13 轮）：
   - **第三定律（白化后 95% 误差对冲陷阱、Schur 补保护与 ERFC 选择性控制）**：在多队列预训练 `EEGNet (f0)` 完成每会话 `support_EA` 白化后，无保护二阶切空间/牛顿更新因病态曲率崩溃 **-4.64 ~ -5.11 pp**（需 **Schur 补 Fisher 信息保护**恢复 **+4.66 pp**，$p_{\text{Holm}}=0.0439$）。然而即便加上保护，横跨第 4–9 轮的交叉拟合收缩（R4）、双侧李群耦合（R5）、Laplace 曲率平均（R6）、时空李群（R7）、SPD 部分传输与保协方差纤维旋转（R8，2,835/2,835 任务）及 GP 核残差锚定（R9，1,548/1,548 任务）全部卡在 `support_EA` 的 BA 平台（$\pm 0.65\text{ pp}$，$p_{\text{Holm}}=1.00$）。51 条件误差重分布审计揭示：`support_EA` 之后的全局微调引发的查询集预测翻转（中位 $D=8.09\text{ pp}$）中有 **95.35% 相互抵消**（$G=+0.01\text{ pp}$），造成 16.7%–30.5% 的会话负迁移。**保留证据的函数式校准（ERFC，R10）** 对 ~84.5% 弱证据查询主动弃权，在三队列（Stieger $n=11$、Pan $n=14$、Weibo $n=10$）上保持与 `support_EA` 和 `matched_map` 同等 BA（$p_{\text{Holm}} \ge 0.5625$）的同时，**削减 83.95–84.83 pp 的查询预测修改**（$p_{\text{Holm}} \le 0.0195$）、**减少 0.69–0.75 pp 的新引入错误**（$p_{\text{Holm}} \le 0.0313$），并将**会话级负迁移率大幅压降 13.33–27.04 pp**！

---

## 仓库目录结构与文件导航

```text
unified-mi-eeg-calibration/
├── README.md                                     # 英文项目总览、三仓库谱系映射与复现指南
├── README_ZH.md                                  # 中文项目总览与核心发现说明
├── manuscript/                                   # 完整旗舰论文、中文对照稿与补充材料包
│   ├── Unified_MIEEG_Manuscript_EN.md            # 英文完整旗舰主稿（Markdown 源码，含表 1-6 与图 1-5）
│   ├── Unified_MIEEG_Manuscript_EN.pdf           # 英文排版预览 PDF (pdflatex 编译)
│   ├── Unified_MIEEG_Manuscript_EN.docx          # 英文可编辑 Word 主稿 (.docx)
│   ├── Unified_MIEEG_Manuscript_ZH.md            # 中文完整对照主稿（Markdown 源码）
│   ├── Unified_MIEEG_Manuscript_ZH.docx          # 中文可编辑 Word 主稿 (.docx)
│   ├── Supplementary_Materials_EN.md             # 补充材料（Tier 2 全量附表 S1-S7 & Tier 3 边界披露表 S8）
│   ├── Supplementary_Materials_EN.pdf            # 补充材料排版预览 PDF
│   ├── Supplementary_Materials_EN.docx           # 补充材料可编辑 Word (.docx)
│   ├── master_experimental_synthesis_zh.md       # 88 分支全量实验盘点与高创新性主线报告
│   └── merger_master_plan_zh.md                  # 三仓库科学主线、统计对齐与工程合并总体规划书
├── figures/                                      # 5 幅出版级多面板组合图（300 DPI PNG + 矢量 PDF + SVG）
│   ├── Fig1_Three_Regime_Synthesis.{png,pdf,svg}
│   ├── Fig2_Regime1_ZeroShot_Cohort_vs_Objective.{png,pdf,svg}
│   ├── Fig3_Regime2_FewLabel_Alignment_and_Mechanisms.{png,pdf,svg}
│   ├── Fig4_Regime3_Neural_Churn_and_Schur_Protection.{png,pdf,svg}
│   └── Fig5_Regime3_ERFC_Selectivity_Tradeoff.{png,pdf,svg}
├── evidence_archive/                             # 从原三仓库提取锁定的只读实验证据包（含 Commit SHA 与 SHA-256）
│   ├── DATA_LINEAGE_MANIFEST.json                # 精确记录每个证据文件对应的原仓库、分支、Commit SHA 与 SHA-256
│   ├── regime1_zero_shot/                        # 源自 jackzhu119/cross-subject-mi-eeg
│   ├── regime2_longitudinal/                     # 源自 jackzhu119/few-shot-mi-eeg
│   └── regime3_prefix_erfc/                      # 源自 jackzhu119/research3
└── scripts/                                      # 零训练、零 GPU 依赖的后处理核验与制图脚本
    ├── verify_all_tables.py                      # 一键核验正文表 1-6 与补充材料表 S1-S8 的全部核心数值
    └── build_svg_figures.py                      # 一键重新生成全部 5 幅 SVG/PNG/PDF 出版级矢量图
```

---

## 一键数据核验与出版级图表复现

无需重跑任何模型训练或 GPU 任务，直接运行以下两条命令即可完成全套数据核验与矢量图重绘：

```bash
# 1. 自动核验正文与补充材料所有核心数值与 evidence_archive/ 原始锁定 CSV/JSON 的一致性
python3 scripts/verify_all_tables.py

# 2. 一键重新生成全部 5 幅出版级矢量图（SVG + 300 DPI PNG + PDF）
python3 scripts/build_svg_figures.py
```
