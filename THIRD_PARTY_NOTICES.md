# 第三方项目来源与许可证

本项目会借鉴下列开源项目的架构、研究流程或策略思想。除非文件内另有明确说明，
本项目的实现均为针对 A 股、本地 FastAPI 服务和现有回测引擎重新编写，不复制其品牌。

| 项目 | 上游地址 | 研究版本 | 许可证 | 本项目借鉴范围 |
|---|---|---|---|---|
| TradingAgents | https://github.com/TauricResearch/TradingAgents | `a33fd4c0f134485a43553a2c23a63cb14adbd88f` | Apache-2.0 | 多角色分析、多空辩论、交易与风险管理流程 |
| daily_stock_analysis | https://github.com/ZhuLinsen/daily_stock_analysis | `f4d9956c527562ba08a1dbc2ca6d20e6b25d4756` | MIT | A 股分析报告、策略问股、操作检查清单 |
| QuantDinger 后端 | https://github.com/OpenByteInc/QuantDinger | `23b1aad65c87ef9c5e5424830e99794075a0e632` | Apache-2.0 | 策略实验、回测、风险参数与运行状态设计 |
| Microsoft Qlib | https://github.com/microsoft/qlib | `79633dd9506ea689e5400dea0197717b5b3d74b7` | MIT | 多因子排序、滚动训练、样本外验证 |

## 使用限制

- QuantDinger 的名称、标志、产品视觉和另行授权的前端不复制。
- 上游项目不会作为本项目运行时依赖，也不会随本地网站一起发布。
- 如果未来直接修改或分发某个上游源文件，必须在该文件保留版权、许可证和修改说明。
- 上游项目的历史回测或宣传数据不作为本网站策略有效性的证据。

## 炸板研究资料

| 来源 | 地址 | 使用范围 |
|---|---|---|
| AKShare 涨停板行情接口 | https://akshare.akfamily.xyz/data/stock/stock.html | 使用其公开文档定义的涨停股池、炸板股池字段；运行时仍通过本项目已有 AKShare 依赖获取数据 |
| QuantFabric / StrikeBoarder 介绍 | https://github.com/QuantFabric/QuantFabric | 仅了解打板、回封板任务边界；StrikeBoarder 为商业功能，不复制其代码、算法或品牌 |
| Wan 等，A 股涨跌停前动态研究 | https://arxiv.org/abs/1503.03548 | 借鉴按市场状态、规模和高频变量分组检验的研究方法 |

炸板概率与复盘实现均为本项目重新编写；第三方研究结论只用于提出候选因子，不作为收益保证。

## 连板与跌停研究资料

| 来源 | 地址 | 使用范围 |
|---|---|---|
| AKShare 涨停股池与跌停股池 | https://akshare.akfamily.xyz/data/stock/stock.html | 使用公开接口字段获取连板高度、封板时间、封单、换手、市值与跌停池；模型实现由本项目重新编写 |
| AKShare API 示例项目 | https://github.com/JoshuaMaoJH/akshare-api | 仅核对涨停池相关接口名称与调用方式，不复制项目代码 |
| Wan 等，涨跌停命中与次日延续研究 | https://arxiv.org/abs/1503.03548 | 用于区分涨停延续与跌停延续/修复，并提示市值、市场状态与命中时点应分组验证 |
| Wan 等，价格限制冷却效应研究 | https://arxiv.org/abs/1803.09422 | 用于提示模型不得把触及涨跌停本身直接解释成确定性延续信号 |

连板晋级和跌停修复基线、时间切分验证、Brier 门槛与版本升级逻辑均为本项目重新实现，不复制第三方策略代码。
