# A股量化资源地图与开发方案

检索日期：2026年10月7日。面向：有股票经验、无需自行编程的个人用户。

本报告整合公开仓库、项目官方文档、数据服务及交易所资料，并给出开发建议。它是第一轮广泛调研，不能代表穷尽互联网。已做文档级核查；尚未逐项安装、拉取行情、运行回测或连接券商。下文“优先”“备选”是工程判断，不代表已验证收益或稳定性。

## 1. 建议结论

构建一套统一的个人量化工作台：数据检查、选股解释、回测、模拟账户、运行日志及后续交易接口。底层采用少量经过验证的组件，其余项目保留为资源库，避免多个框架同时管理资金、持仓和订单。

初步路线：

数据适配器 → 本地历史数据仓库 → 策略/因子 → 交易约束与回测 → 模拟账户 → 中文操作界面。

后续增加：券商适配器 → 订单风控 → 委托回报 → 成交与持仓对账。

第一版优先日线研究与模拟交易。数据层评估 BaoStock、Tushare 与 AKShare；AKShare 按其数据用途声明限定使用范围。回测层首先比较 AKQuant 与 RQAlpha，后者存在授权条件需先厘清。数据库倾向 DuckDB，界面倾向 Streamlit，绩效报告采用 QuantStats。机器学习扩展评估 Qlib；实盘接入评估券商提供的 QMT/xtquant 或 vn.py 支持的证券接口。

这些是待小样本验证的选型建议，不能把“组合方案”理解为已经集成运行。

## 2. 数据与行情资源

| 资源与官方入口 | 能解决什么 | 我们的用途与限制 |
|---|---|---|
| [AKShare](https://github.com/akfamily/akshare) | 多类财经数据接口、公开数据采集 | 研究原型与交叉校验；上游变化可能造成接口失效；项目声明接口及数据用于学术研究，代码许可不等于数据授权 |
| [BaoStock](https://baostock.com/) | A股历史K线、复权因子等 | 日线数据候选；需实测字段、历史覆盖、退市证券与更新时点，不能假定满足全部需求 |
| [Tushare Pro](https://tushare.pro/document/1?doc_id=14) | 标准化证券数据接口 | 行情、财务等数据候选；逐接口核对积分、独立权限、调用频率，不能把客户端开源理解为数据全部免费 |
| [RQData](https://www.ricequant.com/doc/rqdata/python/stock-mod) | A股数据API | 预算允许时评估历史数据与财务数据能力；服务权限、覆盖及报价需按账户确认 |
| [JQData](https://www.joinquant.com/help/api/doc?id=10325&name=JQDatadoc) | 聚宽数据服务 | 备选；本次主站部分页面读取失败，地域访问条件需要再确认，不能直接定为主数据源 |
| [XtData](https://dict.thinktrader.net/nativeApi/xtdata.html) | 迅投行情API | 若券商提供对应环境，可评估研究与执行行情的一致性；实际可用数据由服务权限决定 |

Tushare 的权限说明见[官方服务文档](https://tushare.pro/document/1?doc_id=405)。AKShare 的用途和接口变动说明见[项目介绍](https://github.com/akfamily/akshare/blob/main/docs/introduction.md)。

聚宽官方域名下的[帮助页面](https://test.demo.joinquant.com/help/api/help)显示：自2026年8月1日起停止支持非中国大陆IP访问。该页面位于 test.demo 子域，主站本次读取不完整，因此标记为“需主站或客服进一步确认”，不据此推断用户所在地或可用性。

数据层需要我们自己补上的能力：统一股票代码、交易日历、时区、金额和成交量单位；保留原始数据；记录来源、抓取时点及修订版本；对缺失和异常值报警。数据源之间发生冲突时，记录差异而不是静默覆盖。

## 3. 回测与交易框架

| 项目 | 文档确认的定位 | 选型判断 |
|---|---|---|
| [AKQuant](https://github.com/akfamily/akquant) | Rust/Python研究与交易框架，文档列有T+1、涨跌停等测试 | 优先试验；需独立验证成交规则、Mac安装、数据适配和版本兼容 |
| [RQAlpha](https://github.com/ricequant/rqalpha) | 可扩展回测与交易框架 | A股回测重点候选；需先解决授权边界和数据bundle适配 |
| [vn.py / VeighNa](https://github.com/vnpy/vnpy) | 交易平台框架、多个证券网关及策略模块 | 后续交易执行候选；不能把期货CTA模块直接当作完整A股组合回测器 |
| [WonderTrader](https://github.com/wondertrader/wondertrader) | 量化研发与交易一体框架 | 多策略或性能需求增加时评估；第一版需权衡部署和维护成本 |
| [Hikyuu](https://github.com/fasiondog/hikyuu) | C++/Python策略分析、组合与回测 | 性能和可组合策略研究备选 |
| [QUANTAXIS](https://github.com/yutiansut/QUANTAXIS) | 本地数据、回测、模拟、交易与可视化体系 | 功能广，作为整体架构参考；需要单独验证依赖与组件边界 |
| [Backtrader](https://github.com/mementum/backtrader) | 通用Python回测、指标与经纪商模拟 | 经典实现参考和小型验证工具；A股约束及依赖兼容需要补充验证 |
| [vectorbt](https://github.com/polakowo/vectorbt) | 快速批量策略研究与回测 | 参数研究备选；快速研究结果仍须经过真实交易约束复核，许可有额外条件 |
| [Zipline Reloaded](https://github.com/stefan-jansen/zipline-reloaded) | Zipline延续维护分支 | 研究方法参考；中国市场数据、日历和成交规则需要适配 |
| [LEAN](https://github.com/QuantConnect/Lean) | Python/C#算法交易引擎 | 跨市场架构参考；本次未验证中国境内券商接入，不列为首版主线 |
| [CZSC](https://github.com/waditu/czsc) | 缠论及信号分析工具 | 用户策略确实涉及形态或缠论时再引入 |

维护证据不等于可投产证明。本次查看到 [vn.py Releases](https://github.com/vnpy/vnpy/releases)、[RQAlpha Releases](https://github.com/ricequant/rqalpha/releases)、[Qlib Releases](https://github.com/microsoft/qlib/releases) 和 [AKQuant 更新记录](https://github.com/akfamily/akquant/blob/main/CHANGELOG.md)均有版本记录。未对所有仓库完成提交频率、Issue响应、依赖漏洞与测试覆盖审计，不以Star数判断可靠性。

## 4. 因子、机器学习和研究工具

| 项目 | 可复用能力 | 采用顺序 |
|---|---|---|
| [Qlib](https://github.com/microsoft/qlib) | 数据处理、因子、模型训练、策略研究工作流 | 第二阶段候选；README当前提示官方数据集暂时停用，应准备自己的合格数据 |
| [LightGBM](https://github.com/lightgbm-org/LightGBM) | 表格数据学习、分类和排序 | 简单规则基线建立后，用于比较是否产生额外价值 |
| [Alphalens Reloaded](https://github.com/stefan-jansen/alphalens-reloaded) | 选股因子的预测能力分析 | 检查因子分组、相关性和换手表现 |
| [TA-Lib Python](https://github.com/TA-Lib/ta-lib-python) | 技术指标计算 | 按策略需要使用，核对预热期和缺失值处理 |
| [Optuna](https://github.com/optuna/optuna) | 自动调参和实验管理 | 后续使用；必须限制搜索并保留所有试验记录 |
| [PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt) | 组合优化、风险配置 | 第二阶段；先采用易解释的等权或受限权重基线 |
| [QuantStats](https://github.com/ranaroussi/quantstats) | 收益、回撤和风险报告 | 首版候选；统一收益口径、基准和年化参数 |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 金融强化学习研究 | 保留研究路线，不作为第一版核心 |
| [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 金融文本及大模型研究 | 后续公告、新闻文本实验，先验证时间戳与事实准确性 |
| [RD-Agent](https://github.com/microsoft/RD-Agent) | 自动化数据与模型研发 | 后续实验辅助；控制试验数量与模型调用成本 |
| [Machine Learning for Trading](https://github.com/stefan-jansen/machine-learning-for-trading) | 研究流程和示例代码 | 实现参考，海外市场示例需要A股适配 |

研究方法参考：[The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2326253)。它讨论反复选择回测结果带来的过拟合问题。我们的设计因此需要记录失败实验、时间顺序验证和独立测试集，而不只保留表现最好的策略。

## 5. 实盘接口、存储与界面

| 资源 | 作用 | 实际接入条件 |
|---|---|---|
| [QMT / xtquant](https://dict.thinktrader.net/nativeApi/xttrader.html) | 委托、撤单、持仓、成交和回调 | 券商开通情况、客户端版本及运行环境需确认；API文档可读不代表账户已有交易权限 |
| [vn.py证券网关](https://github.com/vnpy/vnpy) | README列出XTP、TORA、OST、EMT等证券接口 | 根据券商实际提供的接口选择，不预设所有券商可用 |
| [easytrader](https://github.com/shidenggui/easytrader) | 客户端和其他交易通道封装 | 参考；若依赖桌面界面自动化，需评估界面变动和登录状态导致的故障，不优先作为资金执行核心 |
| [DuckDB](https://github.com/duckdb/duckdb) | 本地分析型数据库 | 首版数据仓库候选；配合历史文件快照与备份 |
| [Streamlit](https://github.com/streamlit/streamlit) | Python交互界面 | 首版中文工作台候选；本地运行即可，不必先对外部署 |

以上表格收录33项项目或服务入口，另附许可、更新记录、监管与研究资料。它们存在功能重叠，应通过适配器组合，而不是全部安装在一个环境中。

研究环境与券商执行环境可以分开。当前工作环境是Mac；具体QMT发行版的系统和Python要求应以券商版本核实，不能承诺在这台Mac上直接完成实盘。若需独立Windows执行端，研究端只向其传递经风控的目标订单，执行端负责回报、去重和对账。

## 6. 许可证与数据使用边界

具体版本的LICENSE优先于仓库标签、包元数据和博客介绍。

| 对象 | 本次核查结果 | 对开发的影响 |
|---|---|---|
| [RQAlpha LICENSE](https://github.com/ricequant/rqalpha/blob/master/LICENSE) | 区分非商业与商业用途，商业用途要求米筐授权 | 不能只看到包元数据Apache-2.0就认定任意用途可用；个人交易是否落入其商业定义需澄清 |
| [vectorbt LICENSE](https://github.com/polakowo/vectorbt/blob/master/LICENSE.md) | Apache 2.0加Commons Clause，限制所定义的软件销售用途 | 将其列作源码可用工具，不能描述为无额外限制的宽松开源许可 |
| [Backtrader](https://github.com/mementum/backtrader) | 仓库标注GPL-3.0 | 对外分发组合软件时需要评估许可义务 |
| [AKShare介绍](https://github.com/akfamily/akshare/blob/main/docs/introduction.md) | 数据接口及数据用途声明为学术研究 | 研究原型和生产用途应分别评估，不能仅依据代码许可决定数据使用 |
| Tushare、RQData、JQData、券商行情 | 独立数据服务或接口 | 账户权限、数据保存/展示/再分发范围与代码许可分别核对 |

未列出的项目不代表没有限制。正式采用时锁定版本，保留LICENSE、NOTICE及来源记录；模型权重、数据集和代码也分别核查。

## 7. 我建议自己实现的核心部分

以下是我们的工程设计，尚未编码，也不是现成框架的能力保证。

1. **中文策略说明与版本管理**：把买入、卖出、排除条件和参数变成可读规则，每次改动能比较。
2. **数据可追溯**：每条信号关联数据版本、计算时点和策略版本，能复现“那天为什么选中它”。
3. **历史可见信息控制**：财报按可获取时点使用，保留修订版本；使用当时的成分股与上市状态，不能用今天的股票名单回测过去。
4. **A股成交约束**：按证券类型、板块和生效日期加载规则，支持可卖数量、交易单位、涨跌停、停牌和费用。这里是设计要求，具体规则待实现时逐条核验。
5. **价格口径分离**：特征计算可采用复权序列；订单和持仓现金核算依据实际交易价格及公司行动，避免价格口径混用。
6. **保守成交模拟**：日线不足以判断封板排队成交。无法确认成交时采用保守假设，并将假设显示在报告中。
7. **独立风控**：仓位上限、行业集中度、换手、订单金额、可用现金、重复订单和行情过期检查。阈值以后由用户交易偏好确定。
8. **订单状态与恢复**：区分信号、委托受理、部分成交、成交、撤单和失败；网络超时先查询状态，不盲目重发。
9. **实盘一致性**：程序启动和每日收盘对账，以券商确认的成交与持仓校正本地状态；不一致时阻止新增订单。
10. **研究与AI权限分离**：AI帮助读资料、写策略和解释结果；交易模块只执行结构化、经校验的规则和订单。

## 8. 策略研究候选

先用可解释策略建立基线，再研究复杂模型。以下仅是待验证假设，不构成有效性或收益承诺。

| 假设 | 可量化的候选变量 | 必须重点检查 |
|---|---|---|
| 趋势延续 | 过去若干日收益、突破、均线与成交额 | 震荡期损失、跳空、调仓成本 |
| 相对强弱 | 个股相对市场/行业的收益排序 | 行业暴露、短期反转、排名稳定性 |
| 质量与估值 | 盈利质量、负债、现金流、估值 | 财报披露时点、行业可比性、修订数据 |
| 低波动配置 | 历史波动、回撤、相关性 | 行业集中、市场环境变化 |
| 事件反应 | 公告类别、发布时间、结构化事件 | 新闻重复、事件发生与报道时间混淆 |
| 机器学习排序 | 上述量价和基本面特征 | 数据泄漏、过拟合、跨时期失效 |

第一轮至少保留一个简单规则策略和一个基准组合。各策略使用相同股票池、时间段、费用与可交易约束，才有可比性。

## 9. 集成验证与开发顺序

### 第一步：数据和引擎小样本验证

选择覆盖正常交易、除权、停牌、上市/退市边界等情况的小样本；数据覆盖不足应明确记录。核对两个数据来源的价格、成交量单位、交易日和复权因子。用可手工核算的例子验证引擎持仓、现金、手续费、T+1和部分成交。

产出：数据质量报告、引擎比较结果、锁定的依赖版本。通过后再定主框架，不依据宣传中的性能倍数选型。

### 第二步：可使用的研究工作台

实现数据更新状态、参数设置、股票池、选股理由、回测曲线、最大回撤、换手、费用和交易明细。首版界面让用户通过按钮操作，代码和环境由开发侧维护。

产出：可本地启动的中文程序，以及一套可复现的基线实验。

### 第三步：样本外研究和模拟账户

按时间划分训练、验证和测试区间；标签跨越区间时设置相应隔离。记录所有参数尝试，最终测试区间不用于反复调参。模拟阶段使用每天实际可获取的数据，保留信号、订单与成交假设日志。

产出：样本外表现、费用敏感性、市场阶段分析、模拟与回测差异说明。运行一段时间本身不能证明策略有效，必须覆盖关键异常和足够交易样本。

### 第四步：券商接入

确认券商、账户接口和运行系统后，接入查询、订单回报、风控、对账和异常恢复。先用可用的测试环境验证；实盘规模和交易规则由用户确定。

程序化交易规则会直接影响接口接入。上交所现行页面所列《程序化交易管理实施细则》自2025年7月7日起施行，涵盖个人投资者及报告等要求；定义涉及计算机自动生成或下达交易指令，不能仅以是否手动点击判断适用性。接入前按实际业务向券商核实。[上交所官方细则](https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20250612_10781696.shtml)

## 10. 尚未确定的条件

当前不影响资源调研，但会影响后续开发：用户券商与接口权限、操作系统安排、数据预算、交易频率、股票池范围、持仓与回撤偏好、仅自用或未来对外提供服务。

本轮没有购买服务、下载运行第三方交易程序、连接账户或下单。实际可用性、安装兼容性、数据质量和券商适配仍需上述小样本验证。最终交付应是一套经过验证的工作台，而不是这33项资源的简单堆叠。
