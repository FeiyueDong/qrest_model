# qREST Model Stage 3 完成记录

本文记录 Stage 3 与 Stage 3.5 收口后的源码状态。开发计划分别保留在 `docs/dev/Stage3 观测语义与研究数据集体系开发.md` 和 `docs/dev/Stage3.5 第三阶段收口与基础噪声模型开发.md`；本文只描述已经落地并完成验证的内容。

## 阶段结论

Stage 3 已完成从“可控结构响应生成器”到“结构真值、观测语义和研究数据集分离框架”的主体改造。当前数据链路为：

```text
Model Config
  -> StructuralModel
  -> Backend
  -> Structural Truth
  -> Observation Config
  -> Observation Operator
  -> Clean Observation
  -> Noise Model
  -> Measured Observation
  -> Research Dataset
  -> qREST physical-only export
```

第三阶段最终冻结的核心原则是：

- Structural Truth 由结构模型和后端决定，不随观测布局改变。
- Observation 是从 truth 映射得到的数据，分为 physical sensor 与 virtual probe。
- qREST text dataset 只接收 physical translational observation，不把 `Theta`/`Rz` 伪装成物理通道。
- Noise 是 measurement noise，只作用于 physical observation；truth、derived quantity、modal truth、ground motion 和 virtual probe 保持 clean。
- Research dataset 保存完整研究事实；qREST dataset 保存模拟真实监测输入。

## 完成内容

Stage 2 尾项已经收束：

- `qrest_model.egg-info/` 不再作为跟踪构建产物保留。
- schema 已开始按职责拆分，并保持 `qrest_model.schema` 稳定重导出。
- beam-like 模型观测映射已从 Direct backend 中解耦到 `qrest_model/observations/`。
- Direct/OpenSees provenance metadata 明确记录 matrix、modal 和 response 来源。
- CI 已加入非 OpenSees 常规测试与可手动触发的 OpenSees marker 测试。
- README 已说明 Rayleigh 模型是离散 Rayleigh-type beam，`rotational_inertia` 是节点/楼层集中转动惯量。

观测语义已经落地：

- `AnalysisResult.observations` 成为正式观测入口，`AnalysisResult.sensors` 保留兼容别名。
- `ObservationChannel`/`ObservationResult` 记录 `kind`、`quantity`、`unit`、来源和 observation operator。
- 刚性楼板偏置测点记录包含 `Rz` 的线性观测算子，输出仍可作为 X/Y physical translational observation。
- 单向剪切和 beam-like `U` 观测为 physical translational observation。
- beam-like `Theta` 与刚性楼板 `Rz` 归类为 virtual probe。
- 显式 physical `Theta`/`Rz` 配置会被拒绝。

Research dataset 体系已经落地：

- 单个数据集输出 `manifest.json`、`config.json`、`truth/`、`derived/`、`observations/` 和 `metadata/`。
- `truth/response.npz` 保存完整相对/绝对/地面输入时程。
- `truth/matrices.npz` 保存 `M/K/C` 与 DOF 标签。
- `truth/modal.npz` 与 `truth/structural_properties.json` 保存频率、周期、质量归一化振型、符号约定和 DOF 单位。
- `derived/structural.npz` 与 `metadata/derived.json` 保存层间位移差、层间位移角和 beam-like 层间转角差。
- `metadata/observation.json` 保存每个 channel 的 observation operator，并由 validator 检查 operator 结构、frame、quantity、story、DOF 和系数。
- `manifest.json` 区分 `model_config_hash_sha256` 与 `dataset_config_hash_sha256`；前者标识结构模型，后者包含 observation/noise/research metadata。
- 批量生成会在输出根目录生成集合级 `manifest.json`，汇总每个 case 的 research 标签、truth/observation/derived 摘要和噪声状态。

Stage 3.5 的收口项已经落地：

- `config/research` 以内层 `model_config` 描述结构模型，以顶层 `observations` 作为 research layout 唯一事实来源。
- 旧 `model_config.sensors` 仍作为普通模型和 legacy 输入兼容路径保留。
- 第一版噪声模型位于 `qrest_model/noise/`，支持默认关闭的 physical-only Gaussian white measurement noise。
- 噪声配置支持 `seed`、`model.type = "gaussian_white"`、`model.target = "physical"`、`level.mode = "std_ratio"` 和 `level.value`。
- 噪声启用时，`observations/physical` 保存 measured/noisy observation，`observations/physical_clean` 保存 clean reference，`metadata/noise.json` 保存每个 physical channel 的信号/噪声统计。
- `qrest-model export-qrest` 可直接读取 research dataset，并导出 `observations/physical`；因此噪声启用时 qREST text dataset 使用 measured observation。
- OpenSees imposed support motion 独立验证已经覆盖 shear building 与 Euler beam，Euler case 覆盖 consistent mass 与 base excitation coupling。

## 内置 Benchmark

当前 `config/research/` 包含 9 个 small regression benchmark：

```text
oma_shear_3story
oma_euler_3story
oma_timoshenko_3story
mbi_shear_3story_sparse
mbi_euler_3story_sparse
mbi_rigid_3story_sparse
mbi_rayleigh_3story_sparse
mbi_timoshenko_3story_sparse
mbi_shear_flexure_3story_sparse
```

以及 2 个 research-scale baseline：

```text
oma_shear_12story_research
mbi_timoshenko_16story_research
```

small regression benchmark 用于 CI、pipeline、格式和可复现性验证；research-scale baseline 用于后续 OMA、mode completion 和 model-based identification 研究流程的基准入口。

## 验证记录

第三阶段收尾时通过以下验证：

```bash
.venv/bin/python -m pytest -q tests/test_research_dataset.py tests/test_observation_semantics.py
```

```text
27 passed
```

```bash
env QREST_RUN_OPENSEES_TESTS=1 PYTHONPATH=.:/home/yue/CodeFiles/qrest_module/py_scripts .venv/bin/python -m pytest -q tests/test_opensees_support_motion.py
```

```text
2 passed
```

```bash
.venv/bin/python -m pytest -q -m "not opensees"
```

```text
110 passed, 2 skipped, 19 deselected
```

```bash
.venv/bin/python -m pytest -q
```

```text
110 passed, 21 skipped
```

```bash
env QREST_RUN_OPENSEES_TESTS=1 PYTHONPATH=.:/home/yue/CodeFiles/qrest_module/py_scripts .venv/bin/python -m pytest -q
```

```text
131 passed
```

同时完成：

- `.venv/bin/python -m compileall -q qrest_model tests`
- `git diff --check`

## 冻结边界

第三阶段不包含以下内容：

- colored noise、bias、drift、clipping、missing sample、sensor failure、clock error、orientation error。
- 非线性结构、三维细化有限元、base isolation 或新结构模型族。
- 把 `Theta`/`Rz` 注册为 qREST physical channel；如后续需要真实旋转传感器，应新增明确的 rotational sensor 语义。
- 大规模研究数据库；当前只提供 small regression 与少量 research-scale baseline。
- 全部 beam family 的 OpenSees imposed support motion 独立验证；当前冻结边界为 shear building 与 Euler beam。

## 后续方向

Stage 4 可以在当前稳定数据链上继续推进：

- 扩展噪声族和异常观测模型。
- 引入更复杂的观测布局、缺测和多任务研究数据集。
- 将 research dataset 与 qREST 算法模块的 OMA、mode completion、MBI 流程更紧密对接。
- 为正式研究数据包补充用户文档、案例说明和发布脚本。
