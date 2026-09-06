# qREST Model Stage 3 观测语义启动记录

本文记录 Stage 3 第一批已经落地的观测语义改造。开发计划仍保留在 `docs/dev/Stage3 观测语义与研究数据集体系开发.md`，本文只描述当前源码中的实现状态。

> Stage 3 已完成收口，最终冻结状态见 `docs/history/stage3_completion_qrest_model.md`。本文保留为阶段启动与演进记录。

## 完成范围

Stage 3 已开始把结构完整状态与观测数据分离：

- 新增 `ObservationChannel` 与 `ObservationResult`，每个观测通道记录 `kind`、`quantity`、`unit`、位置、来源和 observation operator。
- `AnalysisResult.observations` 成为新的观测结果入口，`AnalysisResult.sensors` 继续作为兼容别名。
- 旧 `sensors` 配置继续可用，但会归类为 physical sensor 或 virtual probe。
- beam-like 模型的 `Theta` 和刚性楼板的 `Rz` 默认作为 virtual probe，不再默认进入 qREST physical channel。
- qREST metadata/export 默认只使用 physical translational observation。
- 新增 research dataset 出口，目录上分离 `truth/`、`observations/physical`、`observations/virtual` 和 `metadata/`。
- 新增 Model Truth exporter，将完整响应、矩阵和模态真值保存为 NPZ/JSON。
- 批量 research benchmark 会在输出根目录写入集合级 `manifest.json`，汇总每个 dataset 的任务标签、truth/observation/derived 摘要、稳定配置哈希和噪声配置状态。
- `config/research` 的观测布局已收口到顶层 `observations`；`model_config.sensors` 不再作为内置 research case 的第二套布局事实源。
- 已加入 Stage 3.5 第一版 Gaussian white measurement noise，默认关闭；启用后只作用于 physical observation，truth 和 virtual probe 保持 clean。
- qREST text export 已支持直接读取 research dataset，并在噪声启用时导出 measured physical observation。
- 已补充 1 个 research-scale OMA benchmark 和 1 个 research-scale MBI benchmark，与 small regression benchmark 明确区分。

## 当前语义

Structural Truth 表示模型完整状态，例如：

- 刚性楼板：`Ux/Uy/Rz`
- 单向剪切：`U`
- 二维 beam-like 模型：`U/Theta`

Observation 表示从 truth 映射得到的数据，当前分为：

- `physical`：平动物理观测，可进入 qREST Instrument channel。
- `virtual`：结构广义自由度或研究探针，可用于研究数据集、调试和可视化，但不伪装成 qREST 物理通道。

当前单位规则：

- 平动：`m`、`m/s`、`m/s^2`
- 转角：`rad`、`rad/s`、`rad/s^2`

## 架构落点

- `qrest_model/analysis/result.py`：新增 observation channel/operator/result 类型，并保持 sensors 兼容。
- `qrest_model/observations/base.py`：定义 physical/virtual 常量、单位、channel helper 和基础 linear observation operator helper。
- `qrest_model/observations/beam.py`：二维 beam-like 模型观测映射与 channel metadata。
- `qrest_model/observations/shear.py`：单向剪切模型观测映射与 channel metadata。
- `qrest_model/postprocess/sensor_mapping.py`：刚性楼板观测映射补充 channel metadata。
- `qrest_model/exporters/qrest_metadata.py`：qREST physical-only channel 过滤和显式非法 generalized DOF 校验。
- `qrest_model/exporters/qrest_dataset.py`：qREST text dataset 导出，支持从 research dataset 的 measured physical observation 直接导出。
- `qrest_model/exporters/model_truth.py`：完整结构真值导出。
- `qrest_model/exporters/derived_quantities.py`：派生结构量计算与导出。
- `qrest_model/exporters/research_dataset.py`：research dataset 目录、manifest、content summary、noise metadata、derived/observation metadata 和 provenance 导出。
- `qrest_model/datasets/observations.py`：将顶层 research `observations` 展开为 backend 兼容的运行时 sensors。
- `qrest_model/datasets/research.py`：单个与批量 research dataset 生成入口，并生成集合级 collection manifest。
- `qrest_model/datasets/validation.py`：research dataset、noise metadata 与 collection manifest 一致性校验。
- `qrest_model/noise/`：Stage 3.5 基础测量噪声模型，当前支持 physical-only Gaussian white noise 和 `std_ratio`。
- `qrest_model/schema/observation.py`：新增 observation config primitive，为后续配置迁移预留稳定类型。
- `config/research/`：覆盖 6 类 schema model family 的 9 个小规模 deterministic benchmark 配置和 2 个 research-scale benchmark 配置。
- `qrest_model/backends/opensees_support_motion.py`：专用 OpenSees imposed support motion 独立验证 helper，覆盖 shear building 和 Euler beam。
- `qrest_model/cli.py`：新增 `generate-research` 与 `generate-research-cases` 命令。

## 已验证行为

新增测试覆盖：

- legacy beam `Theta` sensor 归类为 virtual probe。
- 显式 physical `Theta/Rz` 配置被拒绝。
- qREST metadata 只导出 physical observation。
- qREST dataset export 按 metadata physical subset 输出数据列。
- 同一结构配置改变 observation layout 时，truth 矩阵、模态和完整响应保持不变。
- beam/shear/rigid-floor observation mapping 输出 kind、unit、channel metadata 和 observation operator。
- research dataset 生成后包含可复现 manifest、truth NPZ、physical/virtual CSV 和 provenance。
- 单个 research dataset manifest 记录 `content_summary`，用于快速读取 time steps、DOF 数、observation 数量、observation quantity 和 derived quantity ID。
- research dataset manifest 区分 `model_config_hash_sha256` 与 `dataset_config_hash_sha256`；前者只标识结构模型，后者包含 observation/noise/research metadata。
- research dataset 生成后包含 `derived/structural.npz` 与 `metadata/derived.json`。
- 派生结构量第一版支持平动层间位移差、层间位移角和 beam-like 层间转角差，并记录单位、shape 和来源。
- modal truth metadata 记录 `mass_normalized` 振型归一化、`largest_abs_component_positive` 符号约定和 DOF 单位。
- research dataset validator 检查 truth 尺寸、observation channel 数量、单位、time consistency 和 physical/virtual 分离。
- research dataset validator 检查 derived quantity 的 metadata 数量、文件存在性、time consistency、shape、finite values 和 unit。
- research dataset validator 检查每个 channel 的 observation operator 结构、frame、quantity、story、DOF 和系数合法性。
- research dataset validator 检查 noise enabled 状态、physical_clean 输出、noise channel 数量和信号/噪声标准差统计。
- collection validator 检查根目录 `manifest.json` 的 dataset count、排序、路径、单个 manifest、observation、derived 和 truth 摘要一致性。
- `DatasetCase` 支持 6 类 schema model family，并保留 research/truth/observation/noise/export policy metadata。
- 批量 research benchmark 能从 `config/research/` 生成并逐项验证。
- 顶层 `observations` 会覆盖旧 `model_config.sensors`，改变 observation layout 会改变 observation 输出但保持 structural truth 不变。
- 同一 noise seed 会生成相同 measured physical observation；不同 seed 会保持相同 truth/clean observation 但产生不同 measured observation；`std_ratio=0` 时 measured 与 clean 一致。
- qREST export 从 noisy research dataset 导出 `observations/physical` measured 数据，而不是 `observations/physical_clean`。
- OMA benchmark 已覆盖 shear、Euler 和 Timoshenko。
- MBI/mode-completion benchmark 已覆盖 shear、Euler、Timoshenko 和 Shear-Flexure。
- OpenSees `MultipleSupport`/`imposedMotion` 专用路径可与 Direct 等效基底惯性输入逐点对照，验证基底输入映射、相对/绝对响应转换、质量项输入，以及 Euler beam consistent mass 与 base excitation coupling。

## 内置研究 benchmark

当前 `config/research/` 包含：

```text
oma_shear_3story                    shear_building_1d
oma_euler_3story                    euler_beam_2d
oma_timoshenko_3story               timoshenko_beam_2d
mbi_shear_3story_sparse             shear_building_1d
mbi_euler_3story_sparse             euler_beam_2d
mbi_rigid_3story_sparse             rigid_floor_shear_3d
mbi_rayleigh_3story_sparse          rayleigh_beam_2d
mbi_timoshenko_3story_sparse        timoshenko_beam_2d
mbi_shear_flexure_3story_sparse     shear_flexure_building_2d
oma_shear_12story_research          shear_building_1d
mbi_timoshenko_16story_research     timoshenko_beam_2d
```

3-story 工况定位为 small regression benchmark，用于 CI、格式、pipeline 和可复现性验证。`oma_shear_12story_research` 是 research-scale OMA baseline，使用 12 层全楼层 X 加速度与多频确定性输入；`mbi_timoshenko_16story_research` 是 research-scale MBI baseline，使用 16 层 Timoshenko truth、5 个 U 加速度 physical observation 和 2 个 Theta virtual probe。

OMA 工况偏全楼层平动物理观测；MBI/mode-completion 工况偏稀疏 physical sensor，并把 `Rz/Theta` 作为 virtual probe 导出。

批量生成输出根目录包含集合级 `manifest.json`，该索引按 case name 排序，并记录每个子 dataset 的相对路径、`research` 标签、`content_summary`、truth 摘要、observation 文件、derived quantity ID 和 `noise.configured` 状态。内置 small regression benchmark 默认不启用噪声，因此 `noise.configured` 为 `false`；显式配置噪声时会额外生成 `observations/physical_clean` 与 `metadata/noise.json`。

## 验证记录

本轮通过以下验证：

```bash
.venv/bin/python -m pytest -q
```

结果：

```text
110 passed, 21 skipped
```

```bash
.venv/bin/python -m pytest -q -m "not opensees"
```

结果：

```text
110 passed, 2 skipped, 19 deselected
```

```bash
env QREST_RUN_OPENSEES_TESTS=1 PYTHONPATH=.:/home/yue/CodeFiles/qrest_module/py_scripts .venv/bin/python -m pytest -q
```

结果：

```text
131 passed
```

同时完成：

- `.venv/bin/python -m compileall -q qrest_model tests`
- `git diff --check`

## 下一步

后续应转入 Stage 4 或正式研究数据包建设：

- 扩展噪声族、缺测和异常观测模型。
- 将 research dataset 与 qREST 算法模块的 OMA、mode completion、MBI 流程更紧密对接。
