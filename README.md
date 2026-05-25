# MAGICAL Sky130 Bridge/Remap Flow

这是一个面向 Sky130 的 MAGICAL bridge/remap 适配版本。目标是让用户在安装外部依赖后，输入一份 Sky130 网表，自动完成 MAGICAL placement/routing、Sky130 GDS 生成、Magic DRC、Magic extraction、connectivity LVS、PEX summary，并输出可用 KLayout 查看的一份最终 GDS。

默认主线 flow 是：

```text
MAGICAL internal GDS
-> remap_gds_to_sky130.py
-> top-port pin label / pin shape postprocess
-> Magic DRC
-> Magic extraction
-> connectivity LVS
-> PEX summary
```

## 当前能力

- 支持 MAGICAL clean netlist。
- 支持 xschem raw Sky130 netlist 转换。
- 自动调用 Docker 内的 MAGICAL placement/routing。
- 自动 remap MAGICAL internal GDS 到 Sky130 drawing layers。
- 自动添加 top-port pin label 和 pin shape。
- 自动运行 Magic DRC 和 Magic raw extraction。
- 自动运行 connectivity LVS，优先使用 `netgen`，缺失时 fallback 到 `netgen-lvs`。
- 自动生成 Magic PEX summary。
- regression 示例重点覆盖 `inverter_core` 和 `ota_core`，额外保留 `current_mirror_core` 作为扩展示例。

## 当前限制

- 默认主线是 bridge/remap flow。
- native Sky130 export 仍是 experimental，不作为默认入口。
- 当前 LVS 是 connectivity LVS，不是 parasitic-aware LVS。
- PEX summary 只统计 Magic raw extraction 中列出的寄生电容，不等于完整后仿。
- Sky130 PDK、Magic、Netgen、KLayout 不随仓库上传，需要用户自行安装。
- generated 大文件、GDS、log、Magic extraction 临时产物不应提交到 GitHub。

## 安装依赖

推荐环境记录：

- WSL2 Ubuntu 24.04.4 LTS
- Kernel: `6.6.87.2-microsoft-standard-WSL2`
- Host Python: Python 3.12.3
- pip: 26.0.1
- python3 path: `/usr/bin/python3`

默认 MAGICAL placement/routing 通过 Docker 运行：

- Docker image: `jayl940712/magical:latest`
- Docker 内 Python: 3.7.5

主机外部命令依赖：

- `docker`
- `magic`
- `netgen-lvs` 或 `netgen`
- 可选：`klayout`

当前验证机器上的路径和版本：

- docker: `/usr/bin/docker`, Docker version 29.4.1
- magic: `/home/to/eda/tools/install/magic-src/bin/magic`, Magic version 8.3.637
- netgen-lvs: `/usr/bin/netgen-lvs`, Netgen 1.5.133

## Python 环境安装

Host 侧 Python 依赖很少，默认只需要 PyYAML：

```bash
python3 -m pip install -r requirements.txt
```

Docker 容器内已有 MAGICAL 所需依赖，例如 `gdspy`、`numpy`、`networkx`、`matplotlib`、`scipy`、`Cython`、`pybind11`、`pyparsing`。这些不是 host requirements。

如果不使用 Docker、选择本地编译 MAGICAL，需要额外准备 `gcc/g++`、`make`、`cmake`、`zlib`、Boost >= 1.6、`flex`、`bison`、Python headers / PythonLibs、`pybind11`、LIMBO、LEMON、Eigen、lp_solve、wnlib、sparsehash、OpenSSL，以及 MAGICAL submodules: ConstGen、IdeaPlaceEx、anaroute、device_generation。

## Sky130 PDK 配置

本仓库不上传 Sky130 PDK。默认查找路径为：

```bash
/home/to/.ciel/ciel/sky130/versions/7b70722e33c03fcb5dabcf4d479fb0822d9251c9/sky130A
```

关键文件：

- `libs.tech/magic/sky130A.magicrc`
- `libs.tech/netgen/sky130A_setup.tcl`

如需覆盖：

```bash
export SKY130A=/path/to/sky130A
```

也可以单次运行：

```bash
SKY130A=/path/to/sky130A python3 tools/sky130_adapter/run_sky130_case_pipeline.py ...
```

## 快速开始：inverter 示例

推荐使用 Python CLI：

```bash
python3 tools/sky130_adapter/run_sky130_case_pipeline.py \
  --netlist examples/inverter_sky130_try/inverter_clean.sp \
  --top-cell inverter_core \
  --vdd VPWR \
  --vss VGND \
  --convert-xschem no \
  --case-name inverter_core \
  --out-dir generated/sky130_cases/inverter_core
```

底层 shell 入口也保留：

```bash
tools/sky130_adapter/run_sky130_case_pipeline.sh \
  --case-name inverter_core \
  --case-dir examples/inverter_sky130_try \
  --top-cell inverter_core \
  --magical-netlist inverter_clean.sp \
  --config inverter.json \
  --vdd VPWR \
  --vss VGND \
  --out-dir generated/sky130_cases/inverter_core \
  --convert-xschem no
```

## 快速开始：OTA 示例

```bash
python3 tools/sky130_adapter/run_sky130_case_pipeline.py \
  --netlist examples/ota_core_sky130_try/ota_core_raw.spice \
  --top-cell ota_core \
  --vdd VDD \
  --vss GND \
  --convert-xschem yes \
  --case-name ota_core \
  --out-dir generated/sky130_cases/ota_core
```

## 自定义 MAGICAL Clean Netlist

clean netlist 可以直接进入 pipeline：

```bash
python3 tools/sky130_adapter/run_sky130_case_pipeline.py \
  --netlist my.sp \
  --top-cell my_cell \
  --vdd VDD \
  --vss GND \
  --convert-xschem no
```

示例格式：

```spice
subckt my_cell A Y VDD GND
M0 (Y A GND GND) sky130_fd_pr__nfet_01v8 l=150n w=1.26u multi=1 nf=2
M1 (Y A VDD VDD) sky130_fd_pr__pfet_01v8 l=150n w=1.26u multi=1 nf=2
ends my_cell
```

## 自定义 xschem Raw Netlist

xschem/ngspice raw netlist 需要转换：

```bash
python3 tools/sky130_adapter/run_sky130_case_pipeline.py \
  --netlist my_xschem.sp \
  --top-cell my_cell \
  --vdd VDD \
  --vss GND \
  --convert-xschem yes
```

转换脚本会处理 `XM` 实例、被注释的 `.subckt/.ends`、`.GLOBAL GND` 等常见 xschem 输出。若 GND 是 `.GLOBAL`，请通过 `--vss GND` 显式作为 top subckt port 注入。`ad/as/pd/ps/nrd/nrs` 等 xschem/ngspice 参数会从 MAGICAL 输入网表中移除，因为真实 layout 寄生由 Magic raw extraction 和 PEX summary 给出。

## 输出文件说明

默认输出目录是 `generated/sky130_cases/<case_name>/`。关键文件包括：

- `summary.md`：本次运行总览。
- `magic_drc.log`：Magic DRC 输出。
- `<top_cell>_extracted.spice`：Magic raw extracted netlist 原始输出。
- `<top_cell>_extracted.raw.spice`：保留寄生的 raw extracted copy。
- `<top_cell>_source.connectivity.spice`：用于 connectivity LVS 的 source netlist。
- `<top_cell>_extracted.connectivity.spice`：用于 connectivity LVS 的 extracted netlist。
- `netgen_lvs_report.out`：Netgen LVS report。
- `lvs_result_summary.md`：connectivity LVS 结果摘要。
- `pex_summary.md`：寄生电容统计。
- 最终 KLayout 可查看 GDS：case 目录中的 `<top_cell>.sky130.pinned_shapes.gds`。

## LVS/PEX 说明

Magic raw extraction 会保留寄生电容。当前 connectivity LVS 会从比较用 netlist 中删除寄生电容和 property-only mismatch，重点验证源网表和版图抽取网表的连通性是否一致。PEX summary 单独统计 raw extraction 中的寄生电容数量和总电容，用于快速检查，不用于当前 LVS 比较，也不等于完整后仿。

## Regression

```bash
tools/sky130_adapter/run_sky130_case_regression.sh
```

case 列表在 `tools/sky130_adapter/sky130_case_registry.yaml`。

## Experimental Native Sky130 Export

当前保留 `MAGICAL_GDS_EXPORT_MAP` native drawing-layer export 试验能力，相关说明见 `docs/sky130_adapter/native_export_experimental.md`。该能力依赖 `flow/python/PnR.py` 和 `anaroute/src/writer/` 的实验修改，不作为默认主线。

## GitHub 上传说明

无说明
