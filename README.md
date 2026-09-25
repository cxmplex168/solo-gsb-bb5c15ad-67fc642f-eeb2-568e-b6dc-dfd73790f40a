# 管网漏点隔离规划台

在无向供水管网上录入**管段、进水点、漏点、必保供水点**以及**绑定管段的阀门**
（最多 14 个，关闭代价为正整数），系统提供四种规划：

1. **常规规划**：计算使全部漏点与全部进水点断开、同时每个必保供水点仍连通
   至少一个进水点的**最低代价关阀组合**。
2. **单阀失效备援规划**：计划关闭的**任意一枚阀门都可能关不上、保持开启**。
   要求方案在正常执行时、以及每一种单阀失效情形（该阀绑定管段保持通水）下，
   全部漏点均与进水点断开、全部必保点仍连通至少一个进水点；在此前提下最小化
   计划关闭阀门的代价总和。
3. **现场执行顺序规划**：对**已保存的可行方案**（常规或备援均可），按方案
   快照为每枚计划阀门录入**正整数操作时长（分钟）**、为每个漏点录入
   **正整数漏水权重**。操作期间该阀仍开启，每步完成后按多进水点连通性更新
   仍通水漏点；求使各操作时段
   **「时长 × 仍通水漏点权重之和」累计暴露量**最小的执行顺序，所有计划
   阀门都要执行，同暴露量取阀门编号序列字典序最小的唯一顺序。入口在
   **历史方案详情**（也可在刚求解出的可行结果下方直接使用），计算只读、
   不修改原方案。
4. **新增阀门选址预览**：对**当前编辑中的管网**，从**尚无阀门的管段**选择
   至多 **6** 个候选位置，各录入**唯一新阀编号、正整数安装费与关阀代价**
   （现有阀门与候选合计 ≤14）。寻找能使全部漏点断开进水点、全部必保点
   仍有水的**增设及关阀方案**：**只为实际关闭的候选阀计安装费**，先最小化
   安装费，再最小化本次关阀代价，仍并列按**新增管段编号列表、关阀编号列表**
   字典序决胜。返回新增位置、费用、关阀清单与供水状态；无解时说明
   **候选范围内不可修复**。**只读试算**：不修改管网，也不写入历史方案。

> 前两种规划同代价时，均取“关闭阀门编号按升序排列后的列表”字典序最小的方案。
> 备援规划无解时会区分：**原本就没有常规可行方案**（`no_base_plan`）与
> **仅缺少备援方案**（`no_failover_plan`，常规方案存在但都扛不住单阀失效）。

- 常规规划无解时给出明确原因（不存在进水点 / 必保点本来就断水 / 漏点有切不断的
  无阀通路 / 任何隔离方案都会饿死某个必保点）。

## 技术栈

Python 3.11 · FastAPI · SQLite（标准库 `sqlite3`）· 原生 HTML/CSS/JavaScript
（无前端构建、无框架）。求解方式：枚举全部阀门子集（≤2¹⁴=16384），对每个
子集做 BFS 连通性判定，保证全局最优。备援规划在此基础上预计算每个子集的
常规可行性，方案 `M` 备援可行当且仅当 `M` 与每个 `M\{j}`（阀门 j 关不上）
均常规可行。执行顺序规划对方案的计划阀门做**子集 DP**（
`suffix[S] = min(d_v·W(S) + suffix[S∪{v}])`，`W(S)` 为关闭集合 S 后仍通水
漏点权重之和，由多进水点 BFS 求出），再正向取字典序最小的最优排列。
选址预览把候选新阀（现有阀门+候选 ≤14）并入管网后**复用同一套图校验、
子集枚举与 BFS 连通性判定**，按（安装费, 本次关阀代价, 新增管段编号列表,
关阀编号列表）的字典序取最优。

## 一键启动

```bash
docker compose up --build -d
```

启动后访问：

| 用途 | 地址 |
| --- | --- |
| 规划台页面（含常规/备援求解与选址预览入口；执行顺序规划入口在历史方案详情内） | http://localhost:8000/ |
| API 健康检查 | http://localhost:8000/api/health |
| 新增阀门选址预览 API | http://localhost:8000/api/plan-siting |
| 执行顺序规划 API（`{id}` 替换为历史可行方案编号） | http://localhost:8000/api/plans/{id}/sequence |
| OpenAPI 文档 | http://localhost:8000/docs |

服务端口固定为宿主机 **8000**（compose 端口映射 `8000:8000`，容器内监听
8000）。容器**首次启动自动建表**，并在空库中写入一份示例管网（页面上点
「载入示例管网」可随时恢复）。停止：`docker compose down`；连同数据一起
删除：`docker compose down -v`。

## 配置

| 配置项 | 方式 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 服务端口 | compose 的 `ports`，如 `"8080:8000"` | `8000:8000` | 宿主机端口可改，容器内固定 8000 |
| SQLite 文件 | 环境变量 `DB_PATH`（Dockerfile 已设） | `/data/pipeline.db` | `/data` 已挂载为命名卷 `pipeline-data` |

## 本地（无 Docker）运行

```bash
pip install -r requirements.txt
DB_PATH=./pipeline.db uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir app
```
首次运行同样会自动初始化数据库并写入示例数据。

## 页面用法

1. **管网输入**：三张表分别维护节点（选角色：进水点/漏点/必保供水点/普通点）、
   无向管段（选两个端点）、阀门（选一条绑定管段并填正整数代价，≤14 个）。
   下方 Canvas 自动绘制力导向管网示意，红色虚线方块表示被关闭的阀门。
2. 点 **求解最优关阀方案**（常规）：依次展示
   - 关阀清单（编号升序、各阀代价、总代价、枚举统计）；
   - 各节点隔离后的供水状态（含每个节点仍连通的进水点）；
   - 各管段状态：`通水 / 已关阀 / 停水`。
3. 点 **求解单阀失效备援方案**：从当前编辑的管网直接发起备援求解，展示
   - **备援关阀清单与总代价**（编号升序、各阀绑定管段与代价）；
   - **逐阀失效校验表**：正常执行 + 计划清单中每一枚阀门“关不上、保持开启”
     两种情形下，全部漏点是否与进水点断开、全部必保点是否仍有供水；任一情形
     不通过会列出仍通水的漏点 / 断水的必保点；
   - 正常执行时的节点供水状态与管段状态。
   - 无解时横幅明确区分 **无备援方案（存在常规可行方案）** 与
     **常规规划本身无解**，并展示最低代价常规方案逐阀失效的校验明细。
4. **新增阀门选址预览**：在输入区下方的选址卡片中点「＋ 添加候选位置」
   （至多 6 行），每行选择一条**尚无阀门**的管段并录入唯一新阀编号、正整数
   安装费与关阀代价（现有阀门与候选合计 ≤14），点 **预览增设及关阀方案**
   后展示
   - **新增阀门位置**（新增管段、新阀编号、安装费、关阀代价）与未采用的候选；
   - **费用**：安装费合计（仅实际关闭的候选阀计费）与本次关阀代价；
   - **本次关阀清单**（现有+新增，编号升序，标注来源）；
   - 各节点供水状态与各管段状态（示意图上新增阀以红色虚线方块标出）。
   只读试算：不修改管网，也不写入历史方案；无解时横幅说明
   **候选范围内不可修复** 及具体原因（含证据通路）。
5. **历史方案**：常规与备援求解都会自动入库，历史表“类型”列区分
   `常规 / 单阀备援`，可回看任一方案及其管网快照（备援方案含全部逐阀失效
   校验结果）。选址预览为只读试算，**不入库**。
6. **现场执行顺序规划**：在第 5 步打开的**方案详情**底部（或刚求解出的可行
   方案结果下方）出现规划卡片：为每枚计划阀门填正整数操作时长（分钟）、为
   每个漏点填正整数漏水权重，点「计算最优执行顺序」后展示
   - 最优阀门顺序、总时长、**累计暴露量**与执行前/完成后的仍通水漏点；
   - 每一步的**起止时间（分钟）**、操作期间仍通水漏点（该阀仍开启，暴露量
     据此计算）、**本步暴露量、刚隔离的漏点、完成后仍通水漏点**与
     **累计暴露量**；
   - 不可行方案不显示入口；录入时遗漏/多余编号或填非正整数会逐条报错，
     计算过程**只读**，原方案与管网快照均不改变。
7. **保存输入**把当前编辑内容落库（求解时也会随方案保存快照，无需先保存）。

> 示例管网中漏点 L 的两条通路各只有一枚阀门（V2、V4），常规方案为
> `V2+V4`（代价 7），但任一枚关不上 L 都会复通，故备援求解返回
> `NO_FAILOVER_PLAN`，可直接在页面上看到逐阀失效校验。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/network` | 读取当前管网输入 |
| PUT | `/api/network` | 校验并整体覆盖管网输入 |
| POST | `/api/plan` | 常规求解并保存方案；请求体可空（用已保存管网），也可直接提交管网 |
| POST | `/api/plan-failover` | **单阀失效备援求解**（独立 API）；请求体规则同 `/api/plan`，复用同一套管网结构与输入校验 |
| POST | `/api/plan-siting` | **新增阀门选址预览**（独立 API，**只读**：不写管网与历史方案）；提交 1~6 个候选位置，管网部分可整体省略 |
| GET | `/api/plans?limit=20` | 最近方案列表（含 `solver`：`base`/`failover`） |
| GET | `/api/plans/{id}` | 方案详情（含节点/管段状态与管网快照） |
| POST | `/api/plans/{id}/sequence` | **现场执行顺序规划**（只读计算，不改原方案）：按快照录入计划阀门时长与漏点权重 |
| POST | `/api/demo` | 恢复内置示例管网 |
| POST | `/api/clear` | 清空管网输入 |

### 请求示例

```bash
curl -X POST http://localhost:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{
    "nodes": [
      {"id":"S","role":"inlet"},
      {"id":"L","role":"leak"},
      {"id":"H","role":"must_keep"},
      {"id":"A","role":"normal"}
    ],
    "segments": [
      {"id":"p1","endpoint_a":"S","endpoint_b":"A"},
      {"id":"p2","endpoint_a":"A","endpoint_b":"L"},
      {"id":"p3","endpoint_a":"A","endpoint_b":"H"}
    ],
    "valves": [
      {"id":"V1","segment_id":"p2","cost":2}
    ]
  }'
```

### 可行响应（节选）

```json
{
  "feasible": true,
  "total_cost": 2,
  "closed_valves": ["V1"],
  "subset_count": 2,
  "isolating_subset_count": 1,
  "node_status": [
    {"id":"S","role":"inlet","supplied":true,"status":"inlet_supply","connected_inlets":["S"]},
    {"id":"H","role":"must_keep","supplied":true,"status":"supplied","connected_inlets":["S"]},
    {"id":"L","role":"leak","supplied":false,"status":"isolated","connected_inlets":[]}
  ],
  "segment_status": [
    {"id":"p2","status":"closed","flowing":false}
  ]
}
```

### 无解响应

`feasible:false`，`reason_code` 取值：

| reason_code | 含义 |
| --- | --- |
| `NO_INLET` | 管网没有进水点 |
| `GUARANTEED_ALREADY_DISCONNECTED` | 一个阀门都不关，已有必保点不通任何进水点 |
| `UNCUTTABLE_LEAK_PATH` | 漏点经**不含任何阀门**的管段连到进水点，无法切断（附一条证据通路） |
| `GUARANTEED_CONFLICT` | 每个能隔离漏点的组合都会使某个必保点失去全部进水点（附在所有方案中都断水的必保点及示例组合） |

`/api/plan` 只可能返回以上四种代码。`/api/plan-failover` 除复用以上代码外，
还可能返回下表代码，并用 `solver:"failover"` 与 `infeasible_kind` 区分两类无解：

| reason_code | infeasible_kind | 含义 |
| --- | --- | --- |
| `NO_INLET` / `GUARANTEED_ALREADY_DISCONNECTED` / `UNCUTTABLE_LEAK_PATH` / `GUARANTEED_CONFLICT` | `no_base_plan` | **原本就没有常规可行方案**（与常规规划同因） |
| `NO_FAILOVER_PLAN` | `no_failover_plan` | **仅缺少备援方案**：存在常规可行方案，但没有任何方案能承受任意单阀关不上 |

### 备援求解请求示例

请求体格式与 `/api/plan` 完全一致。例如漏点唯一通路上有两枚串联阀（任一失效，
另一枚仍可切断漏点）：

```bash
curl -X POST http://localhost:8000/api/plan-failover \
  -H 'Content-Type: application/json' \
  -d '{
    "nodes": [
      {"id":"S","role":"inlet"},
      {"id":"M","role":"normal"},
      {"id":"L","role":"leak"},
      {"id":"H","role":"must_keep"}
    ],
    "segments": [
      {"id":"a","endpoint_a":"S","endpoint_b":"M"},
      {"id":"b","endpoint_a":"M","endpoint_b":"L"},
      {"id":"h","endpoint_a":"S","endpoint_b":"H"}
    ],
    "valves": [
      {"id":"V1","segment_id":"a","cost":1},
      {"id":"V2","segment_id":"b","cost":2}
    ]
  }'
```

### 备援可行响应（节选）

```json
{
  "feasible": true,
  "solver": "failover",
  "total_cost": 3,
  "closed_valves": ["V1", "V2"],
  "subset_count": 4,
  "isolating_subset_count": 3,
  "base_feasible_subset_count": 3,
  "failover_candidate_count": 1,
  "normal_check": {
    "scenario": "normal",
    "failed_valve": null,
    "effective_closed_valves": ["V1", "V2"],
    "leaks_isolated": true, "leaks_reachable": [],
    "keeps_supplied": true, "keeps_starved": [],
    "ok": true
  },
  "failure_checks": [
    {
      "scenario": "valve_failure",
      "failed_valve": "V1",
      "segment_id": "a",
      "cost": 1,
      "effective_closed_valves": ["V2"],
      "leaks_isolated": true, "leaks_reachable": [],
      "keeps_supplied": true, "keeps_starved": [],
      "ok": true
    },
    {
      "scenario": "valve_failure",
      "failed_valve": "V2",
      "segment_id": "b",
      "cost": 2,
      "effective_closed_valves": ["V1"],
      "leaks_isolated": true, "leaks_reachable": [],
      "keeps_supplied": true, "keeps_starved": [],
      "ok": true
    }
  ],
  "node_status": ["…同常规规划（正常执行视角）…"],
  "segment_status": ["…同常规规划（正常执行视角）…"]
}
```

`failure_checks` 对计划清单中的**每一枚阀门**给出一行：该阀关不上、其绑定管段
保持通水时的实际关阀集合、仍可达进水点的漏点（`leaks_reachable`）、断水的
必保点（`keeps_starved`）以及本行是否通过（`ok`）。

### 备援无解响应（仅缺少备援方案）

`feasible:false`、`reason_code:"NO_FAILOVER_PLAN"`、
`infeasible_kind:"no_failover_plan"`；`reason_detail.best_base_plan` 给出最低代价
常规方案（编号升序、总代价）及其逐阀失效校验：

```json
{
  "feasible": false,
  "solver": "failover",
  "reason_code": "NO_FAILOVER_PLAN",
  "infeasible_kind": "no_failover_plan",
  "reason_detail": {
    "base_feasible_subset_count": 1,
    "best_base_plan": {
      "closed_valves": ["V2", "V4"],
      "total_cost": 7,
      "failure_checks": ["…每个计划阀门一行, 结构同上…"]
    }
  }
}
```

### 新增阀门选址预览请求示例

`POST /api/plan-siting`（独立 API，**只读计算**：不修改管网、不写入历史方案）。
请求体中 `nodes/segments/valves` 三者一起提交（当前编辑中的管网），或三者全部
省略（使用已保存管网）；`candidates` 为 1~6 个候选位置，每项含唯一新阀编号
`id`、候选管段 `segment_id`（必须尚无阀门）、正整数 `install_cost`（安装费）
与正整数 `close_cost`（关阀代价）：

```bash
curl -X POST http://localhost:8000/api/plan-siting \
  -H 'Content-Type: application/json' \
  -d '{
    "nodes": [
      {"id":"S","role":"inlet"},
      {"id":"L","role":"leak"},
      {"id":"H","role":"must_keep"}
    ],
    "segments": [
      {"id":"p1","endpoint_a":"S","endpoint_b":"L"},
      {"id":"p2","endpoint_a":"S","endpoint_b":"H"}
    ],
    "valves": [],
    "candidates": [
      {"id":"N1","segment_id":"p1","install_cost":10,"close_cost":2}
    ]
  }'
```

### 选址预览可行响应（节选）

```json
{
  "feasible": true,
  "solver": "siting",
  "install_cost": 10,
  "close_cost": 2,
  "total_cost": 2,
  "new_valves": [
    {"segment_id":"p1","valve_id":"N1","install_cost":10,"close_cost":2}
  ],
  "unused_candidates": [],
  "candidate_count": 1,
  "closed_valves": ["N1"],
  "closed_count": 1,
  "subset_count": 2,
  "isolating_subset_count": 1,
  "node_status": ["…结构同常规规划…"],
  "segment_status": ["…结构同常规规划(候选管段绑定新阀 N1)…"],
  "message": "已找到增设及关阀方案: 新增 1 个阀门(N1(管段 p1)), 安装费 10; 本次共关闭 1 个阀门, 本次关阀代价 2。"
}
```

- `install_cost`：仅对**实际关闭**的候选阀计安装费；`close_cost`：本次全部
  关闭阀门（现有+新增）的关阀代价之和（`total_cost` 同值，与其他求解器字段
  保持一致）。
- `new_valves`：实际采用的新增位置（按新增管段编号升序）；
  `unused_candidates`：未采用（不计安装费）的候选。
- 优化次序：安装费最小 → 本次关阀代价最小 → 新增管段编号升序列表字典序
  最小 → 关阀编号升序列表字典序最小。
- 结果**不含 `id`**：选址预览不入库，历史方案中不会出现。

### 选址预览无解响应

`feasible:false`、`solver:"siting"`，`reason_code` 复用常规规划的四种代码
（`NO_INLET` / `GUARANTEED_ALREADY_DISCONNECTED` / `UNCUTTABLE_LEAK_PATH` /
`GUARANTEED_CONFLICT`，含义见上表），`message` 统一说明**候选范围内不可修复**
（`UNCUTTABLE_LEAK_PATH` 仍附证据通路）。

### 选址预览录入错误（422）

| 场景 | 返回内容 |
| --- | --- |
| 候选位置缺失、为 0 个或超过 6 个 | Pydantic 校验错误 |
| 安装费/关阀代价非正整数（0、负数、小数等） | Pydantic 校验错误 |
| 管网部分只提供了 `nodes/segments/valves` 中的一部分 | `detail.errors`：三者需同时提供或全部省略 |
| 候选管段不存在 / 已绑定阀门 / 被重复选为候选 | `detail.errors` 逐条列明 |
| 新阀编号缺失、与现有阀门重复或候选间重复 | `detail.errors` 逐条列明 |
| 现有阀门与候选合计超过 14 个 | `detail.errors` 逐条列明 |

### 现场执行顺序规划请求示例

对已保存的**可行方案** `id=1` 调用（只读，不入库、不改方案）。`durations`
的键必须**恰好**是方案 `closed_valves` 中的全部计划阀门，`leak_weights` 的键
必须**恰好**是方案快照中的全部漏点，值均为正整数：

```bash
curl -X POST http://localhost:8000/api/plans/1/sequence \
  -H 'Content-Type: application/json' \
  -d '{"durations":{"V2":10,"V4":20},"leak_weights":{"L":5}}'
```

### 执行顺序可行响应（节选）

```json
{
  "ok": true,
  "plan_id": 1,
  "solver": "base",
  "closed_valves": ["V2", "V4"],
  "durations": {"V2": 10, "V4": 20},
  "leak_weights": {"L": 5},
  "initial_flowing_leaks": ["L"],
  "initial_flowing_weight": 5,
  "final_flowing_leaks": [],
  "sequence": ["V2", "V4"],
  "total_duration": 30,
  "total_exposure": 150,
  "steps": [
    {
      "order": 1,
      "valve_id": "V2",
      "segment_id": "s5",
      "duration": 10,
      "start": 0,
      "end": 10,
      "flowing_leaks_during": ["L"],
      "flowing_weight_during": 5,
      "exposure": 50,
      "newly_isolated_leaks": [],
      "flowing_leaks_after": ["L"],
      "flowing_weight_after": 5,
      "cumulative_exposure": 50
    },
    {
      "order": 2,
      "valve_id": "V4",
      "segment_id": "s6",
      "duration": 20,
      "start": 10,
      "end": 30,
      "flowing_leaks_during": ["L"],
      "flowing_weight_during": 5,
      "exposure": 100,
      "newly_isolated_leaks": ["L"],
      "flowing_leaks_after": [],
      "flowing_weight_after": 0,
      "cumulative_exposure": 150
    }
  ]
}
```

- 第 k 步的暴露量 = 该阀时长 × **操作期间**（该阀仍开启，已关闭的只有前
  k-1 枚）仍通水漏点权重之和；`start/end` 为累计分钟时刻，从 0 起算。
- `newly_isolated_leaks` 为本步完成后由通水变隔离的漏点，
  `flowing_leaks_after` 为本步完成后仍通水的漏点；`cumulative_exposure`
  为截至本步的累计暴露量。
- 顺序**唯一**：达到最小累计暴露量的多个排列中，取阀门编号序列字典序
  （按编号字符串比较，如 `V10 < V2`）最小者。
- 方案不关闭任何阀门时返回空 `steps`、`total_exposure: 0`。

### 执行顺序错误响应

| 场景 | HTTP 状态 | 返回内容 |
| --- | --- | --- |
| 方案编号不存在 | 404 | `方案不存在` |
| 目标方案不可行（无解方案） | 422 | `detail.errors` 指明方案不可行及 `reason_code`，不可规划 |
| 遗漏计划阀门时长 / 漏点权重 | 422 | 如 `缺少计划阀门的操作时长: V4`、`缺少漏点的漏水权重: L` |
| 多余编号（非计划阀门 / 非漏点） | 422 | 如 `提供了非计划阀门的操作时长(多余编号): V1`、`提供了非漏点的漏水权重(多余编号): X` |
| 时长或权重不是正整数（0、负数、小数、字符串、布尔、null） | 422 | 如 `阀门 V2 的操作时长必须是正整数(分钟), 收到: 0`、`漏点 L 的漏水权重必须是正整数, 收到: 1.5` |

## 建模约定

- 管段为无向边；每条管段最多绑定 1 个阀门，关阀等价于从图中删除该管段。
- 节点四种角色互斥；漏点本身隔离后为“已隔离”，与漏点处于同一无水分量的
  普通点显示为“断水”。
- 多个漏点必须**全部**与所有进水点断开才算隔离成功。
- **单阀失效备援**：计划关阀集合 M 中每一枚阀门都可能“关不上、保持开启”，
  失效时实际关阀集合为 M 去掉该阀（其余阀门照常关闭）。备援可行要求 M 本身
  及每个 M\\{j} 都满足“漏点全隔离 + 必保点全有水”。失效的仅是“关闭动作”，
  因此计划清单之外的阀门不受影响；不关闭任何阀门的方案天然备援可行。
- 备援规划与常规规划**目标一致**：仅在可行解集合上不同，优化目标仍是计划
  关闭阀门的代价总和最小，同代价按编号升序列表的字典序取最小。
- **现场执行顺序**：计划阀门逐枚操作，操作阀门 v 的时段内 v 仍开启，故该
  时段生效的关阀集合是此前已完成的阀门；暴露量 = v 的正整数时长 × 此时段
  仍通水漏点（与至少一个进水点连通）的正整数权重之和。所有计划阀门都必须
  执行，全部完成后可行方案的漏点必全部隔离。仍通水漏点集合只取决于已关闭
  阀门集合，与顺序无关，因此用 2^k（k=计划阀门数≤14）个子集的子集 DP 求
  最小累计暴露量，并正向构造阀门编号序列字典序最小的唯一最优排列；该计算
  完全只读，不修改原方案与管网快照。
- **新增阀门选址预览**：候选位置只能选在**尚无阀门**的管段上，每个候选录入
  一个**唯一新阀编号**（不得与现有阀门或其他候选重复）、正整数安装费与
  正整数关阀代价；候选至多 6 个，且与现有阀门合计不超过 14 个。求解时把
  候选看作“装上才能关闭”的新阀（关闭代价 = 录入的关阀代价）并入管网，
  复用同一套图校验与连通性判定枚举全部关阀子集；**只有实际关闭的候选阀
  才计安装费**。目标次序为：安装费最小 → 本次关阀代价（全部关闭阀门的
  关阀代价之和）最小 → 新增管段编号升序列表字典序最小 → 关阀编号升序
  列表字典序最小。该规划为**只读试算**：不修改管网、不写入历史方案；
  无解时复用常规无解原因分析，并说明候选范围内不可修复。
