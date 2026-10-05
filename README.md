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

1. 在「考室」可调整最小曼哈顿间距、损坏禁坐开关与损坏格；在「考生」可调整套卷。
2. 打开「排座图」执行排座；座位行说明由统一问题列表投影，违规座位高亮。
3. 在「违规」查看唯一问题列表（损坏禁坐 / 同卷相邻 / 间距不足 / 未排上）。
4. 在「统计」查看由该列表派生的分类计数。

**三口同码**：问题列表（`issues`）是“违规/未排”的唯一真相，行说明、列表、分类计数全部由它派生；前端不另写原因码，文案取自后端下发的 `reason_codes`。同一对座位按 `损坏禁坐 > 同卷相邻 > 间距不足` 短路，只留一句。配置（损坏格/套卷/最小距）变更后经配置指纹自动失效旧方案，三口一起重算。

## 开发与测试

```bash
docker compose exec api pytest -q
```
