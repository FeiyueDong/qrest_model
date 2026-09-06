# qREST Model Stage 4 完成记录

本文记录 Stage 4 在当前源码中的已实现状态。开发计划保留在 `docs/dev/Stage4 研究场景适配与标准数据生成开发.md`；旧版计划保留为 `docs/dev/Stage4 研究场景与算法基准验证开发.old.md`，本文只描述新版简化计划已经落地并通过验证的内容。

## 阶段结论

Stage 4 已完成从 Research Dataset 到 qREST monitoring dataset 的标准数据生成链路收口。当前推荐流程为：

```text
Research Case Config
  -> qrest-model generate-research-cases
  -> Research Dataset
  -> scripts/export_datasets.py
  -> qREST monitoring dataset
  -> monitoring-metadata-derived algorithm config
```

本阶段的核心边界是：

- Research Dataset 保留完整结构真值、完整响应、观测语义、派生结构量和 provenance。
- qREST monitoring dataset 只导出 physical acceleration observation；virtual probe 和 full response truth 不进入监测输入。
- 默认 algorithm config 只从 qREST monitoring metadata 和数据长度推导，不读取真实模态频率、真实振型或完整结构响应。
- stochastic excitation 与 measurement noise 都要求显式 seed 后才能作为可复现随机过程使用。
- `export_datasets.py` 是 Stage 4 推荐的监测数据集转换入口；`build_datasets.py` 与 `map_sensors.py` 保留为 legacy/regression 辅助入口。

## 完成内容

Stage 3/3.5 尾项已经进一步收束：

- 新增 `qrest_model/observations/series.py`，集中处理 observation quantity 归一化、scalar channel series 提取和 noisy row refresh。
- Gaussian measurement noise 对刚性楼板 physical channel 使用标量通道响应，不再对整层 `[X, Y, Rz]` 数组整体注入。
- 噪声启用时必须显式提供 `seed`；噪声后的 observation rows 会与 noisy history 同步刷新。
- Research Dataset 与 qREST Dataset 的 observation CSV 提取逻辑共用同一 scalar series 入口。

Stage 4 新增随机激励：

- `ground_motion.type = "stochastic"` 支持 Gaussian stochastic excitation。
- stochastic excitation 支持 `seed`、`std_x/std_y`、`mean_x/mean_y` 和可选 `band`/`frequency_band`。
- 相同 seed 会生成相同地面输入和结构响应；不同 seed 会改变输入和响应，但结构矩阵与模态真值保持不变。
- 外部地震动文件与 deterministic synthetic ground motion 的兼容路径保持不变。

Research Dataset metadata 已补充 excitation provenance：

- `manifest.json` 与 `metadata/provenance.json` 记录 `excitation.type`、`dt`、`duration`、`seed` 和 `source`。
- `provenance.random_seed` 取自 stochastic excitation seed；deterministic synthetic excitation 时为 `null`。
- `model_config_hash_sha256` 仍只标识结构模型；`dataset_config_hash_sha256` 包含 observation、noise、export policy 和 research metadata。

qREST monitoring dataset 导出链路已经调整：

- `qrest_model.exporters.qrest_dataset` 可直接导出 Research Dataset。
- 噪声启用时导出 `observations/physical` measured data，而不是 `observations/physical_clean`。
- 默认导出会重新生成 `config/`，不再默认复制 generated dataset 的旧配置目录。
- 仅显式传入 `--config-source` 时复制用户指定配置，且不存在时直接报错。

算法配置生成已经去除默认 Truth Leakage：

- `make_algorithm_configs.py` / `write_algorithm_configs()` 不读取 `truth/`、`structural_properties/modal_frequencies.csv`、`mode_shapes.csv` 或 `config.json` 中的结构参数。
- OMA/FDD/SSI-COV 默认 `init_frequencies` 为空。
- 滤波频带根据 `DT` 和 Nyquist frequency 生成。
- IM 使用通用默认特征周期配置。
- MaxEDP `column_position` 来自 qREST channel `LocationXYZ`，而不是结构构件几何。

脚本定位已经收口：

- `scripts/export_datasets.py` 是 Research Dataset / generated dataset 到 qREST monitoring dataset 的主入口。
- `scripts/make_metadata.py` 支持 `--research-dataset`，可从 Research Dataset 生成 qREST metadata。
- `scripts/build_datasets.py` 标注为 legacy/regression dataset 生成入口。
- `scripts/map_sensors.py` 标注为 legacy master time-history 测点映射辅助入口。

## 标准研究 Case

当前 `config/research/` 包含 15 个内置 research case。

9 个 small deterministic regression benchmark：

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

2 个 Stage 3 research-scale baseline：

```text
oma_shear_12story_research
mbi_timoshenko_16story_research
```

4 个 Stage 4 standard research case：

```text
oma_shear_12story_stochastic
oma_timoshenko_12story_stochastic
mbi_timoshenko_16story_sparse_research
rr_shear_12story_sparse_research
```

这些 case 覆盖：

- stochastic OMA：shear 12-story 与 Timoshenko 12-story。
- mode completion / MBI：Timoshenko 16-story medium 与 sparse 两档布局。
- response reconstruction：shear 12-story sparse physical observation。

## 端到端验证

本阶段收尾时完成了新增标准 case 的端到端 smoke：

```bash
.venv/bin/python -m qrest_model.cli generate-research-cases \
  --output-root /tmp/qrest_model_stage4_cases \
  --case mbi_timoshenko_16story_sparse_research \
  --case rr_shear_12story_sparse_research \
  --validate
```

结果摘要：

```text
mbi_timoshenko_16story_sparse_research: time_steps=501, physical_channel_count=3, virtual_channel_count=2
rr_shear_12story_sparse_research: time_steps=501, physical_channel_count=4, virtual_channel_count=0
dataset_count=2
```

随后完成 qREST monitoring dataset 转换：

```bash
.venv/bin/python scripts/export_datasets.py \
  --input /tmp/qrest_model_stage4_cases \
  --output /tmp/qrest_model_stage4_qrest
```

抽查结果：

```text
mbi_timoshenko_16story_sparse_research: ChannelNum=3, data_shape=(501, 3)
rr_shear_12story_sparse_research: ChannelNum=4, data_shape=(501, 4)
```

生成目录包含：

- `<dataset>_data.txt`
- `<dataset>_metadata.json`
- `config/preprocess/`
- `config/rr/`
- `config/edp/`
- `config/oma/`
- `config/im/`

OMA config 中 `init_frequencies` 为空，符合 no truth leakage 约束。

## 验证记录

本阶段收尾时通过以下验证：

```bash
.venv/bin/python -m pytest -q tests/test_research_dataset.py
```

```text
25 passed
```

```bash
.venv/bin/python -m pytest -q
```

```text
118 passed, 21 skipped
```

```bash
env QREST_RUN_OPENSEES_TESTS=1 PYTHONPATH=.:/home/yue/CodeFiles/qrest_module/py_scripts .venv/bin/python -m pytest -q
```

```text
139 passed
```

同时完成：

- `.venv/bin/python -m compileall -q qrest_model tests scripts`
- `git diff --check`
- `scripts/build_datasets.py --help`
- `scripts/map_sensors.py --help`
- `scripts/export_datasets.py --help`
- `qrest-model export-qrest --help`

## 冻结边界

Stage 4 不包含以下内容：

- benchmark evaluator、algorithm runner 或 MAC scoring framework。
- 大规模排列组合式研究数据库。
- colored noise、bias、drift、clipping、missing sample、sensor failure、clock error 或 orientation error。
- 把 virtual probe 或 full response truth 默认写入 qREST monitoring dataset。
- 让默认算法配置读取真实模态信息或结构真值。
- 新的非线性结构、新模型族或三维梁细化模型。

后续阶段可以在当前标准数据链路之上继续建设算法侧评估、更多噪声/异常观测模型，以及面向正式研究数据包的发布流程。
