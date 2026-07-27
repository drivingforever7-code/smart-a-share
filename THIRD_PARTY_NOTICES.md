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
