# HallSpan 考场间距排座

在考室网格上按最小曼哈顿距离排座，同试卷套不得四邻相邻，并输出违规与统计。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4900 |
| API | http://localhost:9900 |
| API 文档 | http://localhost:9900/docs |
| Postgres | localhost:5450 |

健康检查：`GET http://localhost:9900/api/health`

## 使用说明

1. 在「考室」「考生」「试卷套」确认基础数据。
2. 打开「排座图」执行排座：可改最小曼哈顿距、切换损坏禁坐、点击空格标记损坏格、在名册下拉改套卷，改完三口（行说明 / 违规与未排列表 / 分类计数）随一次重排同源更新。
3. 在「违规」查看统一 findings 列表（违规与未排）及其派生分类计数。
4. 在「统计」查看占用与按原因码分类的派生汇总。

## 唯一真相与原因码

- 未排与违规只有 **findings 列表**一个真相源；行说明、违规/未排列表、分类计数全部由它派生，引擎内不再各算一套（派生结果有运行时自检，对不齐即整场失败）。
- 同一对座位只短路出一个原因码，优先级：`seat_blocked`（损坏禁坐）> `same_paper_adjacent`（同卷相邻）> `distance`（间距不足）；未排另有 `capacity_full`（座位已满）。
- 原因码与中文标签只定义在后端 `REASON_CODES`，前端只按不透明 key 取 `label/tone`，不另写原因码。
- 未启用损坏禁坐时 `seat_blocked` 计数必须为 0，冒码即整场失败；成功且列表为空时所有分类计数为 0。

## 开发与测试

```bash
docker compose exec api pytest -q
```
