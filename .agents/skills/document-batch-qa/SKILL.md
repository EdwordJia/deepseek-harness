---
name: document-batch-qa
description: 执行租赁诉讼文书批量生成后的 QA 闭环：调用文书生成 API、轮询批次、下载包含 QA 未通过稿的完整交付包、对照人工案件信息表和金额修正表生成差异报告，并把待复核/待填写状态保留到汇总结果。用户提到批量文书、人工表对照、QA 拦截稿、案件汇总表、文书生成接口或按平台整理被告文书时使用。
---

# 文书批量 QA

把批量文书处理成“可审计、可复核、可交付”的流水线。先以人工案件信息表和金额修正表建立权威口径，再生成或读取批次；QA 未通过的案件仍保留可审阅成稿，但不得冒充正式交付件。

## 工作流

1. **确认输入和口径**
   - 确认资料根目录、平台/批次、预期案件数、人工案件信息表和 `修改模板.xlsx`（若有）。
   - 以订单号/案件号作为主键，不以被告姓名或目录名作为唯一键。
   - API 地址从 `DOCUMENT_API_BASE_URL` 读取；默认使用 `https://qmjkuymwasqg.sealoshzh.site`。本地联调可设为 `http://127.0.0.1:8000`。
   - 不把账号、Token、身份证号或手机号写进技能、命令行历史或报告；通过环境变量和 DSH 的私有配置注入。

2. **启动或接续批次**
   - 本机资料上传后启动（推荐）：
     `python scripts/document_batch_qa.py upload-start --root-dir <资料根目录> --case <被告名> --max-cases 1 --wait --download-dir <输出目录>`
   - `upload-start` 保留相对目录，并自动包含共享原告材料和根目录人工表；不要把 Windows 本机路径直接作为线上 `root_dir`。
   - 新批次运行：
     `python scripts/document_batch_qa.py start --root-dir <资料根目录> --wait`
   - 已有批次运行：
     `python scripts/document_batch_qa.py status <batch_id> --wait`
   - 默认保留 `strict=false`，让缺字段案件进入 QA；除非用户明确要求硬失败，不要用 strict 模式把可复核稿丢掉。
   - AI 不可用时只有在用户确认后才启用 `--quick-draft-if-ai-unavailable`，并在报告中标注这是草稿。

3. **轮询和判断终态**
   - 轮询 `GET /api/v1/workflows/document-generation/batch/{batch_id}`，直到 `completed`、`completed_with_errors` 或 `failed`。
   - 记录 `total_cases`、`generated_cases`、`completed_cases`、`needs_review_cases`、`failed_cases` 和每个 case 的 QA 状态、缺失字段、输出目录。
   - 只有真正没有输出的失败案才算不可下载；`needs_review` 但有 docx 的案件必须继续进入下载包。

4. **下载完整包和汇总表**
   - 使用 `download` 子命令下载批次 ZIP；不要根据“QA 未通过”过滤掉案件。
   - 同时下载 `case_info_excel`（若 API 返回），并保留批次 JSON 状态和 QA 报告。
   - 下载后计算 SHA-256，报告中记录 URL、文件名、大小和哈希，便于复核同一产物。

5. **审计和人工表对照**
   - 运行：
     `python scripts/document_batch_qa.py audit --zip <batch.zip> --human-table <案件信息表.xlsx> --amount-table <修改模板.xlsx> --report <qa-report.json>`
   - 先检查数量和主键覆盖，再比较字段；不要先改文书正文。
   - 金额以 `修改模板.xlsx` 为准（总租金、剩余本金、已付金额、买断价、到期买断价、违约金金额等）。
   - 身份信息、法院、案由、设备/串码、合同日期和逾期日期以人工案件信息表为准；逾期天数应按文书生成日期重新计算。
   - 管辖约定必须能回溯到合同 OCR 原文；人工表不能替代合同条款证据。
   - 对照失败时输出“字段、生成值、权威值、来源、严重级别”，不要静默覆盖。

6. **修正和再生成**
   - 优先修正 `case_data`、人工表映射或抽取规则，再调用批次再生成；不要用脚本直接替换 docx XML 来掩盖结构化数据错误。
   - 先用 `preview-data <batch_id> --output preview.json` 保存原始结构，再准备仅含权威差异的覆盖 JSON。
   - 用 `regenerate-preview <batch_id> --overrides-json overrides.json --wait` 应用覆盖并再生成；复核无误后执行 `confirm-preview <batch_id> --wait --download-dir <输出目录>`。
   - 每次修正保留原 ZIP，使用新的批次/版本目录；报告中关联旧批次和新批次。
   - 重新生成后至少检查：诉状金额、保全金额、逾期日期/天数、管辖条款原文、原告公章和法人章是否分别存在且未串入被告信息。

7. **按平台整理和交付**
   - 交付目录按平台/批次分组，组内按订单号或被告目录保存，不混合不同平台。
   - 输出 `delivery-manifest.json`：每案主键、平台、文书数量、QA 状态、待填写项、ZIP 内路径和哈希。
   - 正式交付只允许 QA 通过；待复核/待填写稿另放 `review/`，但必须保留下载链接和完整文书，供人工处理。

## 质量门

- 案件数：人工表有而未生成的订单必须列入 `scope_exclusions` 或阻断交付；生成目录有而人工表无的历史案必须显式列为未标注，不得混入准确率。
- 主键：订单号重复、同一订单对应多个被告或姓名串号均为 blocker。
- 金额：总租金、剩余本金、已付金额、违约金基数、保全金额与权威表不一致为 blocker。
- 文书：检测到未解析 token、0 元金额、错误日期、缺少应有的代理函/授权书、公章或法人章缺失为 blocker。
- 证据：管辖条款、租转售/买断条款只有 AI 结论而没有原文引用时，标记待复核，不得自动放行。
- 隐私：报告中的身份证号和手机号必须脱敏；原始文件只保存在用户指定的本地目录。

## 资源

- `scripts/document_batch_qa.py`：启动、轮询、下载、ZIP/DOCX/XLSX 审计和摘要生成。
- `references/api.md`：DSH 调用的 API、状态字段和人工表映射口径。

## 输出约定

报告至少包含：`batch_id`、时间、API 地址（不含 Token）、输入根目录、案件计数、QA 计数、主键覆盖、差异列表、blocker 数、待复核数、下载文件哈希、scope exclusions 和下一步动作。没有报告就不要声称批次已完成。
