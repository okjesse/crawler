# 批次质量评测：holdout_L3

- 人数：40
- 抓取级别：[('L3', 40)]

## 字段填充率

| 字段 | 人数 | 比例 |
|---|---|---|
| 邮箱 | 38 | 95% |
| 职称 | 40 | 100% |
| 研究方向 | 37 | 92% |
| 入职年份 | 23 | 57% |
| 人才头衔 | 13 | 32% |
| 招生招聘 | 3 | 8% |
| 电话 | 21 | 52% |
| 办公地点 | 23 | 57% |
| 可确认英文论文 | 37 | 92% |
| ORCID | 35 | 88% |
| h 指数 | 36 | 90% |
| 论文致谢基金号 | 36 | 90% |
| 课题组规模 | 27 | 68% |
| 方法章节 | 25 | 62% |
| 品牌 | 22 | 55% |
| 竞品耗材记录 | 9 | 22% |
| 课题组网站 | 7 | 18% |
| 实验技术标签 | 37 | 92% |

## 职称与学院列表页交叉比对

- 可比对 40 人，一致 40 人（100%）。

## 邮箱

- 有邮箱 38 人，其中本校域名 37 人。
- 来源：heuristic 38（heuristic=主页，api=论文，input=名单）

  - 非本校域名：刘慧娟 liumiaomiao333@hotmail.com

## 论文归属

- 已归属论文 774 篇；依据：full 275, orcid 247, email 159, seed 92, initial 1。
- 有强锚点（邮箱、主页论文、ORCID）的老师 35/37。
- 待确认同名论文合计 527 篇。

- 提示分布：姓名检索结果超过 300 条（常见姓名），只核对了最新的 3…（30）；1 篇论文作者同名同校但院系对不上，未计入统计…（5）；4 篇论文作者同名同校但院系对不上，未计入统计…（4）；19 篇论文作者同名同校但院系对不上，未计入统计…（3）；13 篇论文作者同名同校但院系对不上，未计入统计…（3）；46 篇论文作者同名同校但院系对不上，未计入统计…（2）

## 人工抽查：仅凭姓名与院系归属的论文（随机 25 篇）

| 老师 | 研究方向 | 论文 | 作者单位 | 判断 |
|---|---|---|---|---|
| 龚清秋 | 合成生物学；细胞生物学 | [2024 MCTP controls nucleocytoplasmic partitioning of AUXIN RESPON](https://pubmed.ncbi.nlm.nih.gov/39423818/) | State Key Laboratory of Microbial Metabolism & Joint International Research Labo |  |
| 贺林 | 遗传学和生物信息学；药物基因组学 | [2024 Engineering cyanobacteria as a new platform for producing ta](https://pubmed.ncbi.nlm.nih.gov/39014505/) | Bio-X Institutes, Key Laboratory for the Genetics of Developmental and Neuropsyc |  |
| 王威 | Glycerol；Shikimic Acid | [2026 Iterative precursor rebalancing improves phenazine-1-carboxy](https://pubmed.ncbi.nlm.nih.gov/42324039/) | State Key Laboratory of Microbial Metabolism, School of Life Sciences and Biotec |  |
| 程海荣 | 氧化葡糖杆菌类细菌细胞膜结合蛋白催化多元醇生成非2-酮...；解脂耶氏酵母合成其 | [2025 Threitol, a Novel Functional Sugar Alcohol Biosynthesized by](https://pubmed.ncbi.nlm.nih.gov/40724359/) | State Key Laboratory of Microbial Metabolism, School of Life Sciences and Biotec |  |
| 贺光 | Genetic Associations and Epidemiology；Sc | [2021 Structure and Membrane Targeting of the PDZD7 Harmonin Homol](https://pubmed.ncbi.nlm.nih.gov/33937240/) | Key Laboratory for the Genetics of Developmental and Neuropsychiatric Disorders, |  |
| 孙冬雷 | 成像学研究病原真菌与宿主互作；肺部细菌感染时空动态 | [2022 Neuronal miR-29a protects from obesity in adult mice](https://pubmed.ncbi.nlm.nih.gov/35490865/) | Sheng Yushou Center of Cell Biology and Immunology, Department of Genetics and D |  |
| 曹骎 | 基于Aβ与其天然受体相互作用的阿尔兹海默症诊疗药物研发；基于结构的纤维化抑制剂设 | [2026 Cryo-EM Structures of Sunflower Amyloid Fibrils Reveal Two D](https://pubmed.ncbi.nlm.nih.gov/42801496/) | Bio-X Institutes, Key Laboratory for the Genetics of Developmental and Neuropsyc |  |
| 黄婷婷 | 酶催化反应的机理和应用；微生物来源天然产物生物合成基因簇的克隆和表征 | [2022 Chirality-influenced antibacterial activity of methylthiazol](https://pubmed.ncbi.nlm.nih.gov/35063710/) | School of life Sciences and Biotechnology, Shanghai Jiaotong University, Dongchu |  |
| 曹骎 | 基于Aβ与其天然受体相互作用的阿尔兹海默症诊疗药物研发；基于结构的纤维化抑制剂设 | [2026 Myoglobin Amyloid Fibrils Reveal a Hierarchical Principle of](https://pubmed.ncbi.nlm.nih.gov/42378159/) | Bio-X Institutes, Key Laboratory for the Genetics of Developmental and Neuropsyc |  |
| 贺光 | Genetic Associations and Epidemiology；Sc | [2023 Waist circumference mediates the association between rs12603](https://pubmed.ncbi.nlm.nih.gov/37081070/) | Bio-X Institutes, Key Laboratory for the Genetics of Developmental and Neuropsyc |  |
| 庞小燕 | 人和动物的肠道微生物组研究
主要为人和动物的肠道微生物组研究 | [2019 Quantification of Human Oral and Fecal Streptococcus parasan](https://pubmed.ncbi.nlm.nih.gov/31921079/) | State Key Laboratory of Microbial Metabolism, School of Life Sciences and Biotec |  |
| 贺光 | Genetic Associations and Epidemiology；Sc | [2026 DeepGene-BC: Deep Learning-Based Breast Cancer Subtype Predi](https://pubmed.ncbi.nlm.nih.gov/41749823/) | Bio-X Institutes, Key Laboratory for the Genetics of Developmental and Neuropsyc |  |
| 邓子新 | 微生物次级代谢产物的生物合成；DNA硫修饰生物学 | [2025 Molecular Insight into the Recognition of DNA by the DndCDE ](https://pubmed.ncbi.nlm.nih.gov/40565227/) | State Key Laboratory of Microbial Metabolism, School of Life Sciences & Biotechn |  |
| 谢志平 | 细胞自噬(Autophagy)
是对维持真核生物健康有关键作用的的一类亚细胞降解 | [2022 The entry of unclosed autophagosomes into vacuoles and its p](https://pubmed.ncbi.nlm.nih.gov/36227834/) | State Key Laboratory of Microbial Metabolism, School of Life Sciences and Techno |  |
| 陆婷婷 | 多组学、生物信息学；生物信息学、基因组学 | [2026 A CD138+ tumor-associated macrophage/Siglec-F+ neutrophil fe](https://pubmed.ncbi.nlm.nih.gov/41818263/) | Bio-X Institutes, Key Laboratory for the Genetics of Developmental and Neuropsyc |  |
| 夏小霞 | 人工蛋白质材料的加工及生物医学应用；人工无膜细胞器驱动的微生物代谢重塑 | [2019 Cellulosic ethanol production: Progress, challenges and stra](https://pubmed.ncbi.nlm.nih.gov/30849432/) | State Key Laboratory of Microbial Metabolism, Joint International Research Labor |  |
| 邓子新 | 微生物次级代谢产物的生物合成；DNA硫修饰生物学 | [2025 The Final Steps in Pseudoiodinine Biosynthesis Feature Ring-](https://pubmed.ncbi.nlm.nih.gov/40747071/) | State Key Laboratory of Microbial Metabolism, School of Life Sciences and Biotec |  |
| 黄婷婷 | 酶催化反应的机理和应用；微生物来源天然产物生物合成基因簇的克隆和表征 | [2024 Cytochrome P450 Mining for Bufadienolide Diversification](https://pubmed.ncbi.nlm.nih.gov/38624108/) | State Key Laboratory of Microbial Metabolism, Joint International Research Labor |  |
| 贺光 | Genetic Associations and Epidemiology；Sc | [2019 GRIK4 and GRM7 gene may be potential indicator of venlafaxin](https://pubmed.ncbi.nlm.nih.gov/31083176/) | Bio-X Institutes, Key Laboratory for the Genetics of Developmental and Neuropsyc |  |
| 万春玲 | 精神分裂症氧化还原失衡的机制研究；基于代谢异常的精神分裂症分子诊断研究 | [2024 Genome-Wide and Exome-Wide Association Study Identifies Gene](https://pubmed.ncbi.nlm.nih.gov/39457610/) | Bio-X Institutes, Key Laboratory for the Genetics of Developmental and Neuropsyc |  |
| 万春玲 | 精神分裂症氧化还原失衡的机制研究；基于代谢异常的精神分裂症分子诊断研究 | [2025 Attenuated Niacin Skin Flushing Response in Diabetic Periphe](https://pubmed.ncbi.nlm.nih.gov/40277306/) | Key Laboratory for the Genetics of Developmental and Neuropsychiatric Disorders, |  |
| 蹇华哗 | 典型深海环境中的病毒研究
1；深海病毒的生存策略（lytic/lysogenic | [2023 Potential Role of Lysine Acetylation and Autophagy in Brown ](https://pubmed.ncbi.nlm.nih.gov/37347174/) | State Key Laboratory of Microbial Metabolism, School of Life Sciences and Biotec |  |
| 邓子新 | 微生物次级代谢产物的生物合成；DNA硫修饰生物学 | [2026 Hippuric acid metabolism by Corynebacterium glucuronolyticum](https://pubmed.ncbi.nlm.nih.gov/42710493/) | State Key Laboratory of Microbial Metabolism, Joint International Research Labor |  |
| 邓子新 | 微生物次级代谢产物的生物合成；DNA硫修饰生物学 | [2025 Molecular insights fast-tracked: AI in biosynthetic pathway ](https://pubmed.ncbi.nlm.nih.gov/40130306/) | State Key Laboratory of Microbial Metabolism, Joint International Laboratory on  |  |
| 邓子新 | 微生物次级代谢产物的生物合成；DNA硫修饰生物学 | [2024 The LysR family transcriptional regulator ORF-L16 regulates ](https://pubmed.ncbi.nlm.nih.gov/38784197/) | Key Laboratory of Combinatorial Biosynthesis and Drug Discovery, Ministry of Edu |  |

## 待核问题分布

- 另有 1 ：5
- 另有 4 ：4
- 另有 19 ：3
- 另有 13 ：3
- 缺研究方向：3
- 未找到可确认归属的英文论文：3
- 另有 46 ：2
- 缺邮箱：2
- 详情页内容过少：2
- 另有 26 ：1
- 另有 5 ：1
- 另有 9 ：1
- 另有 33 ：1
- 另有 22 ：1
- 另有 25 ：1
- 另有 15 ：1
- 另有 23 ：1
- 另有 17 ：1
- 另有 27 ：1
- 另有 29 ：1
- 邮箱非本校域名：1
- 另有 2 ：1
- 另有 67 ：1
- 另有 18 ：1
