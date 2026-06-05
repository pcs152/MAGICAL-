# 不完善之处与后续改进清单

## 记录格式

```text
### YYYY-MM-DD 阶段 / 模块

- 问题：
- 为什么重要：
- 后续动作：
- 状态：open / in_progress / resolved
```

## 当前记录

### 2026-06-01 全阶段 / 过程管理

- 问题：每个阶段跑通后仍会存在不完善之处，需要集中记录，避免讨论过的问题散落在聊天里。
- 为什么重要：后续从 V0 走到 V1/V2/V3/V4 时，需要知道哪些问题只是暂时绕过，哪些问题必须补齐后才能进入论文、展示或工程主线。
- 后续动作：之后用户说“记录：...”时，将对应内容追加到本文件，并标明阶段、问题、影响和下一步。
- 状态：open

### 2026-06-01 V1 / 寄生风险规则解释

- 问题：当前 `risk_report.json` 采用第一版启发式规则，只能解释输出节点、偏置节点、差分输入失配和 Magic 未映射内部重寄生节点，阈值仍然是经验值。
- 为什么重要：V1 可以说明“哪里可能有风险”，但还不能证明“这个风险一定导致某个性能指标下降”；后续需要和 `prelayout_metrics.json`、`postlayout_metrics.json`、`pre_post_diff.json` 绑定。
- 后续动作：V1 后续补 `risk_rulebook.yaml`，把规则阈值、适用电路类型、对应性能指标和回退建议从代码里抽出来。
- 状态：open

### 2026-06-01 V1 / Magic 匿名内部网络映射

- 问题：`ota_core` 的 Magic PEX 中出现 `a_25_264#`、`a_425_364#` 这类未映射内部网络，V1 只能标记为 `large_unmapped_extracted_net`，暂时不能对应回前端网表里的 `net1/net2`。
- 为什么重要：如果不能把后版图内部寄生映射回前端节点，就只能做粗粒度“后端回看”，很难精确指导 sizing、约束生成或寄生感知模型训练。
- 后续动作：补一个 extracted-net 到 source-net 的映射任务，优先研究 Magic/LVS 输出中是否保留可用的节点对应关系。
- 状态：open

### 2026-06-01 环境 / 完整 pipeline 重跑

- 问题：尝试完整重跑 `inverter_core_post_cleanup` 时，Magic 8.3.105 在读取 `7b70722e33c03fcb5dabcf4d479fb0822d9251c9/sky130A.tech` 的 DRC 阶段发生 segmentation fault；日志中先出现多条 `defaultsidewall`、`device` 等 techfile extract 语法错误。
- 为什么重要：V1 增量流程已能消费已有真实 PEX 样本，但完整 MAGICAL -> Magic -> LVS -> PEX -> V1 pipeline 目前被本机 Magic/PDK 兼容性阻塞。
- 后续动作：单独建立环境修复 task，确认师兄推荐 Magic 版本、sky130A hash 与本机 `magic --version` 的兼容组合；在修复前不要把完整重跑失败误判为 V1 规则脚本失败。
- 状态：open

### 2026-06-01 环境 / Sky130 诊断报告

- 问题：`diagnose_sky130_environment.py` 确认当前环境为 `environment_status=fail`，疑似问题为 `magic_pdk_incompatibility`；当前 Magic 为 `8.3.105`，PDK hash 为 `7b70722e33c03fcb5dabcf4d479fb0822d9251c9`，最近完整 pipeline 失败阶段为 `magic_drc`。
- 为什么重要：这说明 V1 的增量 JSON 诊断可以继续，但完整“MAGICAL 版图生成 -> Magic DRC/PEX -> 样本生成”链路暂时不能作为稳定样本生产线。
- 后续动作：向师兄确认已跑通环境的 Magic 版本、PDK hash、Docker 镜像和是否在容器内跑 Magic；随后固定一套 known-good 环境配置。
- 处理结果：后续确认仓库外层已有 `scripts/env/magical_sky130_env.sh` 和 `scripts/env/bin/magic` wrapper；source 该环境后，`magic` 走 `efabless/openlane:latest` 容器中的 Magic 8.3.483，而不是宿主机 `/usr/bin/magic` 8.3.105。用该环境重跑 `inverter_core_post_cleanup` 已通过 `magic_drc`、Magic extraction、LVS、PEX 和 V1 Harness 诊断，`diagnose_sky130_environment.py` 更新为 `environment_status=pass`。
- 状态：resolved

### 2026-06-01 环境 / 使用方式约束

- 问题：若没有先 `source /home/qlf/IOT/scripts/env/magical_sky130_env.sh`，pipeline 会继续使用宿主机 `/usr/bin/magic` 8.3.105，仍可能在 `magic_drc` 阶段失败。
- 为什么重要：后续进入 V2 跑 NMCF/DFCFC2 等新网表时，环境入口不一致会造成“同一代码有人能跑、有人不能跑”的问题。
- 后续动作：后续应把快速开始文档和 pipeline preflight 明确为“先 source env 脚本”，或让 `run_sky130_case_pipeline.py` 自动提示当前 `magic` 路径和版本。
- 状态：open
