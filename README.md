# 材料试验室签报台

耐磨涂层试验室用签报结果安排复测。登记员依据规程固定族额度、检验编号、零假设成功率和显著性水平。台架员提交逐片成败并收到封批修订。分析员选择明确的检验和修订生成计算稿，柜台接纳并兑现后，质控员按原号领取证据、核账并安排下一轮复测。交班发生失答时，分析员可用原请求号续查、重投或办理撤办。台架后续更正生成独立的新修订，既有报告仍指向实际使用的样本。

## 运行

使用 Python 3.11 标准库。在项目根目录执行完整正常回归和样例。

```sh
python3 -B check_project.py
python3 -B -m analysis.workbench demo samples/shift.json
```

回归入口由运行环境提供。演示从样例读取数据，通过业务接口写入独立的临时工作区，输出在发布失答、重开、撤办和批次更正后的实际结果。传入 `--workspace` 时需指定已有目录，演示使用该目录下独立的临时子目录。

## 应用接口

Python 使用 `with Workspace(path) as work`，`Workspace` 从 `analysis.workbench` 引入。`initialize_workspace(path)` 可以单独初始化。正常 CLI 命令通过 `--workspace` 选择工作区，无需预先执行 `init`。以下是一次正式签报及原号核对。

```sh
python3 -B -m analysis.workbench --workspace shift-work init
python3 -B -m analysis.workbench --workspace shift-work register coating 500 A 1/2 300
python3 -B -m analysis.workbench --workspace shift-work seal cycle-1 '[["01",true],["02",true],["03",true],["04",true],["05",true],["06",true]]'
python3 -B -m analysis.workbench --workspace shift-work request a A cycle-1 1
python3 -B -m analysis.workbench --workspace shift-work publish a
python3 -B -m analysis.workbench --workspace shift-work status a
python3 -B -m analysis.workbench --workspace shift-work cancel a
python3 -B -m analysis.workbench --workspace shift-work read R-a
python3 -B -m analysis.workbench --workspace shift-work audit coating
```

| API | 输入及结果 |
| --- | --- |
| `register(family_id, limit_bps, test_id, null_rate, alpha_bps)` | 原子保存固定族与规程。Python 接受 `Fraction` 或整数零假设成功率。相同输入复用原登记。`registration(test_id)` 可查询。 |
| `seal(batch_id, trials)` | 接受逐片的 `(trial_id, passed)` 或 `TrialResult`。试片按身份排序。与当前内容相同的重投返回当前修订，更正追加修订。`batch(batch_id, revision)` 读取精确修订。 |
| `request(request_id, test_id, batch_id, revision)` | 保存原申请和冻结计算稿。同号同参复用，修改参数或给同一个检验分配异号会报错。`application(request_id)` 读取分析库当前已知结果。 |
| `publish(request_id)` | 按同族余额接纳，接纳后可兑现。成功返回 `published` 和原报告号。`insufficient` 表示本次投递未占额，之后可显式重投。 |
| `cancel(request_id)` | 原申请已撤办时返回 `cancelled`。若公开先成立，返回 `published` 和原号。 |
| `status(request_id)` | 核对柜台的持久结果。柜台尚无终局且分析台也无已知终局时，返回 `pending`。 |
| `read(report_id)` | 领取冻结正文、原号回执和精确父批。原号为 `R-` 后接原请求号。 |
| `audit(family_id)` | 返回上限、正式占额、在途承诺和实际可用余额，均以整数基点表示。 |

标识符使用非空白字符串并保留原值。检验号在工作区内唯一。空批、非布尔记录以及任何重复试片身份都会拒绝整批。整数族上限为 0–10000，整数登记水平为 1–10000。零假设成功率能取闭区间 [0,1] 的有理数。参数冲突及非法输入报告 `ValueError`，缺少登记、批次、申请、族或可领报告报告 `KeyError`。CLI 的这些输入错误以非零状态退出。`pending`、`insufficient`、`cancelled` 与 `published` 是可识别的业务答复。

单侧二项上尾以有效试片总数 n、成功数 k 和固定零假设成功率 p₀ 为输入，精确求和 i 从 k 至 n 的概率，包含 k。p≤α 时显著。10000 基点等于 1，显著与不显著的报告均按原登记水平计费。零次成功时上尾为 1，p₀ 的端点按退化分布处理。Python 返回 `Fraction`。JSON 分子和正分母为约分后的十进制字符串。

## 可领、撤办与恢复

工作区内有准备、分析和柜台三个 SQLite 库。重复初始化只补建缺少的结构。受理将额度保存为在途承诺。兑现将承诺转为正式占额，并一次提交正文、原号和公开裁决。撤办在柜台先成立时永久拦住原申请迟到的接纳和兑现，并释放已有承诺。公开先成立时，报告保持可领，撤办返回已公开原号。正式占额与在途承诺共同决定可用余额。

`Workspace.publish` 可接收事件回调，阶段依次为 `before_admission`、`after_admission`、`before_commit`、`after_commit`。首次兑现调用才经过提交阶段。`Workspace.cancel` 支持 `before_cancel` 和 `after_cancel_commit`。回调可抛出 `desk.settlement.ReplyUnavailable` 模拟失答。兑现的 `before_commit` 位于写事务内，抛出时正文、回执和公开裁决一并回滚，先前已提交的承诺可续办。`after_commit` 的失答保留柜台的公开事实。柜台仍可在不知回包是否送达时以原号裁决后续操作。柜台模块的低层函数接收来自分析库的可信已提交申请，兑现和查询会核对持久绑定。

样例中，六片全成的甲得到 1/64，发布提交后失答，重开撤办时返回原报告。500 基点的族在甲占用 300 后拒绝乙的 300。丙的五片四成得到 3/16，虽不显著也占用 200。更正甲所用批次后，甲仍能按原号领取六片全成的第一修订。
