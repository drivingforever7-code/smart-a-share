# 智选 A 股

智选 A 股是一套在本机浏览器中运行的 A 股量化选股网站，重点服务短线与波段交易。

它提供：

- 交易时间实时行情和市场概览
- 短线、波段两套综合评分
- 建议买入、小仓位试买、观察、暂不建议和回避五档判断
- 每条建议对应的理由、风险、参考关注区间和失效条件
- 条件选股、系统预设方案和 CSV 导出
- 日内分钟 K 线及日、周、月 K 线
- 不偷看未来数据的策略验证
- 浏览器本地自选股和筛选方案

## 最简单的启动方法

首次使用：

1. 安装 Node.js 20 或更高版本。
2. 安装 Python 3.11 或 3.12，安装时勾选 Add Python to PATH。
3. 右键“安装依赖.ps1”，选择“使用 PowerShell 运行”。
4. 安装完成后双击“启动网站.bat”。

当前电脑已经存在项目专用虚拟环境时，可以直接双击“启动网站.bat”。

网站地址：

    http://127.0.0.1:5173

后端接口文档：

    http://127.0.0.1:8710/docs

使用结束后回到启动窗口按回车，本地服务会自动停止。

## 数据说明

- 实时行情优先使用 AKShare 的东方财富接口。
- 东方财富中断时自动切换到腾讯证券备用接口。
- 腾讯全市场接口较慢，因此备用状态下会使用更长缓存。
- 已有缓存时页面先立即显示缓存，后台再更新。
- 所有页面都会显示数据来源、获取时间和缓存状态。
- 免费数据源可能延迟、中断或临时限制访问，系统不会用随机数据冒充真实行情。

AKShare 是面向研究的数据接口工具，公开网站阶段需要重新评估数据授权、稳定性和服务容量。参考 [AKShare 官方介绍](https://akshare.akfamily.xyz/introduction.html)。

## 手动开发

启动后端：

    backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8710 --reload

启动前端：

    npm run dev

运行检查：

    npm run build
    backend\.venv\Scripts\python.exe -m pytest backend\tests -q

## 目录

    src/                 React 前端
    backend/app/         FastAPI、数据源、评分与回测
    backend/tests/       后端核心规则测试
    backend/data/        本地 SQLite 数据库（不会提交到 Git）
    AGENTS.md            产品与开发唯一权威文档

## 重要提示

量化结果仅基于历史和当前公开数据，不保证未来表现。网站中的“建议买入”是规则信号，不代表收益承诺，投资决策和风险由用户自行承担。
