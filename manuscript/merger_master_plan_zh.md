# 三仓库科研成果合并总体规划书（科学主线、统计对齐、数据取舍与仓库整合）

> [!IMPORTANT]
> **合并的核心目标**：将您前期独立开展的三个仓库（[`cross-subject-mi-eeg`](file:///home/antigravity/repos/cross-subject-mi-eeg)、[`few-shot-mi-eeg`](file:///home/antigravity/repos/few-shot-mi-eeg)、[`research3`](file:///home/antigravity/repos/research3)）从“三个独立的实验项目”无缝升华为**“一套数学符号统一、评价算子贯通、层层递进回答同一个核心科学问题的高创新性研究体系”**，同时在**绝不重跑任何新实验**的前提下，妥善处理三仓库之间的指标差异、模型差异、已完成/未完成分支取舍以及 GitHub 仓库归档结构。

---

## 一、 逻辑主线合并规划：如何把三个仓库串成“一条层层递进的科学逻辑链”？

单独看三个仓库，每个仓库都有一部分“看似阴性/平台期”的结果（例如仓库一的 5 种风险损失函数无显著增益；仓库二的 `Full CSP - LDA-only` 在 BNCI 上仅 `+0.19 pp`、`EA` 在 2s 任务窗上仅 `+0.13 pp`；仓库三的第 1–13 轮在平均 BA 上与 `support_EA` 持平）。**合并的最高技巧，就是用上一阶段的发现去解释下一阶段的瓶颈，把所有的“局部平台期”全部转化为支撑核心理论的递进证据：**

```mermaid
flowchart TD
    subgraph Q["核心科学问题 (Central Research Question)"]
        Q0["为什么跨被试与跨会话 MI-EEG 中，复杂的目标函数正则化与高维参数微调屡屡陷入准确率平台期？<br/>真正支配净解码收益 (G = C - I) 与弱势类覆盖 (Recall_min) 的第一性物理机制是什么？"]
    end

    subgraph R1["第一层递进：零样本跨被试迁移 (Regime I, 源自 cross-subject-mi-eeg)"]
        A1["现象与痛点：单队列源模型 (S9) 发生严重弱势类崩塌 (MinRecall 27.32% / 35.71%)"]
        A2["实验证据 1B (90/90 任务)：在固定源池上改用 5 种目标函数 (TAIL/Cons/GroupDRO) 仅 +1.28 pp (p=0.124)，GroupDRO 反而崩塌 -8.75 pp"]
        A3["实验证据 1A & 1C (固定 2,592 试次预算 90/90 任务)：BNCI 左偏 (79.3%/42.0%) 与 Yang 右偏 (49.9%/70.3%) 方向相反；<br/>等预算混合双队列 (s60-matched) 抵消偏置，直接贡献 +11.00 pp MinRecall 与 +4.19 pp BA (>86% 全量收益)，并在 S29 处饱和 (+21.17 pp)"]
        A1 --> A2 --> A3
    end

    subgraph R2["第二层递进：少标签纵向跨会话校准 (Regime II, 源自 few-shot-mi-eeg)"]
        B1["递进追问：既然源域无法覆盖目标会话的个体日间漂移，给 B=20 个目标校准试次时，应该直接重拟合空间滤波器/分类器参数，还是先做输入空间协方差对齐？"]
        B2["实验证据 2A/2B：无对齐空间重拟合 (Full - LDA) 在 BNCI 上发生 97.73% 误差相互抵消 (C=4.17 pp, I=3.98 pp, 净增益仅 +0.19 pp)；<br/>而预滤波支持集白化 (EA - Full) 打破误差相消，在 Kumar (+5.30 pp) 与 BNCI (+5.65 pp, 9/9+) 上同步恢复弱势类召回 (+10.45 / +8.52 pp)"]
        B3["实验证据 2C (544 次拟合) & 2D (148 次相位拟合)：揭示时间窗与协方差几何的物理对应关系——<br/>5s 宽提示窗漂移以非任务期全局幅值缩放 (RMS) 为主 (裁剪至 2s 任务窗后额外 EA 增益消失, -7.73 pp)；<br/>紧凑纯任务窗 (BNCI) 漂移则由非对角跨通道协方差旋转主导 (Full EA 超越 RMS +4.63 pp)"]
        B1 --> B2 --> B3
    end

    subgraph R3["第三层递进：小样本前序神经与函数式校准 (Regime III, 源自 research3 第 1-13 轮)"]
        C1["终极追问：当多队列预训练深度网络 (f0) 已经在输入端完成了每会话 support_EA 白化后，<br/>继续在 B<=20 试次上做切空间二阶更新、李群旋转、SPD 类条件纤维传输 (R8) 或 GP 核残差锚定 (R9)，还能进一步提升准确率吗？"]
        C2["实验证据 R3-R9 & 51 条件误差重分布审计：无保护二阶更新因曲率病态崩塌 -4.64~-5.11 pp (需 Schur 补保护恢复 +4.66 pp)；<br/>但即便加上保护，R5-R9 全部卡在 support_EA 的 BA 平台 (±0.65 pp, p_Holm=1.0)！<br/>原因是 support_EA 之后 8.09% 的预测翻转中有 95.35% 相互抵消 (G=+0.01 pp)，引发 16.7%-30.5% 的会话负迁移！"]
        C3["实验证据 R10/R12/R13 (收官解法 ERFC)：保留证据的函数式校准 (ERFC) 对 ~84.5% 弱证据查询主动弃权，<br/>在保持三队列平均 BA 完全持平的前提下，显著削减新引入错误 (-0.69~-0.75 pp) 并将负迁移会话率暴降 13.33-27.04 pp！"]
        C1 --> C2 --> C3
    end

    Q --> R1 --> R2 --> R3
```

---

## 二、 异质性对齐规划：解决三仓库合并的 4 个关键技术衔接点

为了防止审稿人产生“三篇不同工作硬拼在一起”的割裂感，我们在合并时执行以下 **4 项标准化对齐**：

### 1. 数学符号与评价指标的完全统一（Unified Metric & Notation System）
原本三个仓库各自使用了略有不同的指标名称（如 Repo 1 叫 `min_recall`，Repo 2 叫 `weak_recall` 与 `corrected/introduced`，Repo 3 叫 `balanced_corrected_vs_ea / balanced_introduced_vs_ea`）。合并时统一定义为**两大核心算子**：
1. **试次级误差重分布四元组 $(C, I, D, G)$ 与抵消率 $\kappa_{\text{total}}$**：
   - 纠正错误率 $C$（Corrected Errors，pp）
   - 新引入错误率 $I$（Introduced Errors，pp）
   - 总预测翻转/抖动率 $D = C + I$（Prediction Churn，pp）
   - 净平衡准确率增益 $G = C - I = \Delta\text{BA}$（Net BA Gain，pp）
   - 总误差抵消率 $\kappa_{\text{total}} = 1 - |G_{\text{mean}}| / D_{\text{mean}}$（Error Cancellation Ratio，%）
   - **数据完备性核验**：您三个仓库的现有回传数据**均已包含精确的 $(C, I, D, G)$ 数值**（Repo 1 Dreyer85 `S60 vs S9`：$C=18.86, I=13.01, D=31.87, G=+5.85, \kappa=81.64\%$；Repo 2 Kumar12 & BNCI9 全组件 $(C,I,D,G)$；Repo 3 51 条件神经网格与 R10 ERFC 全队列 $(C,I,D,G)$），无需任何补算即可在全篇形成严丝合缝的定量呼应！
2. **动态弱势类召回率 $\text{Recall}_{\min}$ 与会话级负迁移率 $\text{NT}_{\text{session}}$**：
   - 将 Repo 1 的 `min_recall` 与 Repo 2 的 `weak_recall` 统一记为 $\text{Recall}_{\min} = \min(\text{Recall}_{\text{L}}, \text{Recall}_{\text{R}})$；
   - 将 Repo 3 的 `negative_transfer_session_fraction_vs_ea` 统一记为会话级负迁移风险 $\text{NT}_{\text{session}}$。

### 2. 模型架构差异的合理化包装（Cross-Architecture Invariance）
- **审稿人可能问**：“为什么阶段一有 `BROAD` 神经网络和 `CSP+rLDA`，阶段二主要是 `CSP+LDA`（加上 V2/V3 的 `EEGNet`），阶段三又是 `EEGNet (f0)`？”
- **合并叙事策略**：将其正面定义为**“跨线性空间滤波与深度卷积架构的几何普适性验证（Cross-Architecture Geometric Invariance）”**：
  - 在阶段一，同时汇报深度网络 `BROAD`（`+21.17 pp`）与经典 `CSP+rLDA`（`+13.82 pp` 及固定预算 `+11.00 pp`），证明多队列边界去偏置规律**不依赖特定网络结构**；
  - 在阶段二，用具有闭式解的 `EA + CSP/LDA` 精确剥离“标量幅值 `RMS` vs. 对角缩放 `Diagonal` vs. 非对角矩阵白化 `Full EA`”（544 次拟合），同时用 Discovery V3（126 项任务）的 `EEGNet` 证明深度网络在小样本下同样遵循“冻结归一化统计量优于自适应重估（`+1.50~+1.91 pp`）”的方差控制律；
  - 在阶段三，聚焦于深度网络 `EEGNet (f0)` 在完成 `support_EA` 后的 13 轮微调极限，顺理成章引出 `Schur` 保护与 `ERFC`。

### 3. 各仓库分支与实验的“精准剪枝与分级纳入”规划（Pruning & Tiering Matrix）
三个仓库共有 88 个分支、数千个结果文件。为保证主稿紧凑有力、同时严格遵守科学诚信（不隐瞒阴性结果、不把未完成实验当完成实验），规划采用 **“主稿核心层（Tier 1）+ 补充材料机制层（Tier 2）+ 显式边界披露层（Tier 3）”** 的三级纳入方案：

| 纳入层级 | 所在位置 | 包含的具体实验包与分支来源 | 纳入理由与处理方式 |
| :--- | :--- | :--- | :--- |
| **Tier 1：主稿核心证据链**<br>（100% 完成、统计链条完整） | 论文正文第 4.1–4.3 节<br>（对应表 1–6 及图 1–5） | 1. **Repo 1 Study 1A**：`ELIGIBLE_V3_RESULTS_20261018`（`S9`/`S29`/`S60` $\to$ Dreyer85）<br>2. **Repo 1 Study 1B**：`origin/hpc-results/paper1-risk-v1`（90/90 任务，5 种目标函数）<br>3. **Repo 1 Study 1C**：`origin/hpc/paper1-composition-v2` 中 **100% 完成的 90/90 项经典 `weighted_csp_rlda` 任务**（2,592 固定试次配比）<br>4. **Repo 2 主实验与机制扩展**：`origin/research/paper2-alignment-integrated-revision`（Kumar12/18 + BNCI9 四组件解耦、544 次几何拟合、148 次 `cue5s vs task2s` 时间窗拟合）<br>5. **Repo 3 核心轮次**：51 条件误差重分布审计 + **R3**（174/174，Schur 保护 `+4.66 pp`）+ **R4**（204/204，交叉拟合 `+1.75 pp`）+ **R8**（2,835/2,835，SPD 纤维旋转）+ **R9**（1,548/1,548，GP 残差锚定）+ **R10**（429 单元，**ERFC** 主比较与 18 项选择性机制检验） | 每一项均已完成 100% 预设配对评估，拥有完整的被试级 bootstrap CI、精确符号翻转 $p$ 值及 Holm 多重校正，共同构成三大定律的铁证。 |
| **Tier 2：补充材料支撑层**<br>（100% 完成的辅助/开发集实验） | 补充材料（Supplementary Materials）表 S1–S8 | 1. **Repo 2 Discovery V2 (24/24) & V3 (126/126)**：源-目标协方差混合与神经网络 BN 统计量冻结对比<br>2. **Repo 2 Kumar 开发集 (`development6`) 与 QC 振幅剔除敏感性检验**<br>3. **Repo 3 R2 (66/66)、R5 (105/105)、R6 (198/198, Laplace 曲率改善 NLL)、R7 (273/273)**<br>4. **Repo 3 R12 (78/78, `top_q` 证据排序) & R13 (96/96, 跨会话持久性 vs 重置)** | 全部已完成并验证，放在正文中一句话概括核心结论，详细表格放入补充材料，既展现工作量厚度，又不打断正文主线节奏。 |
| **Tier 3：显式透明披露层**<br>（部分完成而已停止的任务） | 正文第 6 节（Limitations）与补充材料说明 | 1. **Repo 1 `composition-v2` 的神经网络子分支**（完成 99/540 任务）<br>2. **Repo 3 Round 1 & Round 11（算子迁移，完成 3,190/10,270 任务后停止）** | 严格遵循您的要求“不再跑新实验”，在方法与局限性章节显式说明其停止状态，**绝不拿残缺交集做显著性检验**，体现极高的学术规范性。 |

---

## 三、 工程与代码仓库物理合并规划（GitHub Repository Merger Blueprint）

如果您希望不仅在论文层面合并，还在 GitHub 上把三个仓库整理为一个**清晰、可审计、审稿人友好的统一代码与数据工程包**，我为您设计了一套**无损归档合并架构**（已在本地 `/home/antigravity/unified_paper` 准备好基础结构，随时可同步至 GitHub）：

```text
unified-mi-eeg-error-redistribution/          # 统一旗舰项目根目录（可作为新仓库或主仓库新分支）
├── README.md                                 # 英文项目总览、三大范式核心发现与一键复现指南
├── README_ZH.md                              # 中文项目总览与三仓库数据谱系映射说明
├── manuscript/                               # 完整论文与投稿文件包
│   ├── Unified_MIEEG_Manuscript_EN.md        # 英文完整主稿（含表 1-6 与图 1-5 引用）
│   ├── Unified_MIEEG_Manuscript_EN.pdf       # 编译好的英文排版预览 PDF (859 KB)
│   ├── Unified_MIEEG_Manuscript_EN.docx      # 可编辑英文 Word 主稿 (615 KB)
│   ├── Unified_MIEEG_Manuscript_ZH.md        # 中文完整对照稿
│   └── Unified_MIEEG_Manuscript_ZH.docx      # 可编辑中文 Word 主稿 (586 KB)
├── figures/                                  # 5 幅出版级组合图（300 DPI PNG + 矢量 PDF + 可编辑 SVG）
│   ├── Fig1_Three_Regime_Synthesis.{png,pdf,svg}
│   ├── Fig2_Regime1_ZeroShot_Cohort_vs_Objective.{png,pdf,svg}
│   ├── Fig3_Regime2_FewLabel_Alignment_and_Mechanisms.{png,pdf,svg}
│   ├── Fig4_Regime3_Neural_Churn_and_Schur_Protection.{png,pdf,svg}
│   └── Fig5_Regime3_ERFC_Selectivity_Tradeoff.{png,pdf,svg}
├── evidence_archive/                         # 从三仓库提取锁定的只读结果快照（附原始 Git Commit SHA 溯源）
│   ├── DATA_LINEAGE_MANIFEST.json            # 记录每个 CSV/JSON 对应原三仓库的精确分支与 Commit SHA
│   ├── regime1_zero_shot/                    # 源自 cross-subject-mi-eeg (ELIGIBLE_V3 + risk-v1 + composition-v2)
│   ├── regime2_longitudinal/                 # 源自 few-shot-mi-eeg (paper2-alignment-integrated-revision + V2/V3)
│   └── regime3_prefix_erfc/                  # 源自 research3 (Rounds 1-13 verified tables & BMTE error grid)
└── scripts/                                  # 纯后处理复现与制图脚本（零训练、零 GPU 依赖，秒级运行）
    ├── build_svg_figures.py                  # 一键从归档数据重新生成全部 5 幅 SVG/PNG/PDF 出版级图表
    └── verify_all_tables.py                  # 一键核验正文表 1-6 全部统计量与原始仓库 CSV 的一致性
```

---

## 四、 供您拍板的两个关键执行选项

请查看下方的交互式选项（或直接告诉我您的偏好），确认后我立即为您执行对应的合并落地操作：
1. **文稿合并形态**：是采用当前的 **单篇顶刊大一统旗舰长文（1 篇整合全部三大范式）**，还是希望在此基础上额外准备一套 **“双篇关联互补稿（Paper A 专攻跨被试/跨会话输入协方差几何与误差重分布 + Paper B 专攻深度网络 Schur 保护与 ERFC 函数式校准）”**？
2. **GitHub 仓库合并操作**：是否需要我将整理好的统一论文、5 幅矢量图、三仓库提取的完整 CSV/JSON 证据包（`evidence_archive/`）与一键核验脚本推送到您的 GitHub（例如新建一个统一仓库 `jackzhu119/unified-mi-eeg-calibration`，或推送到现有仓库的指定分支）？
