# 文书批量 API 参考

## 基础地址

从 `DOCUMENT_API_BASE_URL` 读取。不要把认证信息拼入 URL。当前线上默认地址是 `https://qmjkuymwasqg.sealoshzh.site`，本地开发地址通常是 `http://127.0.0.1:8000`。

## 端点

### 上传本机目录

`POST /api/v1/uploads/oss/local-batches`

使用 multipart form 同时发送重复的 `relative_paths` 和 `files` 字段，二者顺序及数量必须一致。响应中的 `materialized_root` 是后续批量生成接口可读取的服务端目录；不要把本机 `D:\...` 路径直接发送给线上批量接口。

### 启动批次

`POST /api/v1/workflows/document-generation/batch/start`

```json
{
  "root_dir": "D:/cases/platform-batch",
  "strict": false,
  "quick_draft_if_ai_unavailable": false,
  "preview_mode": false,
  "max_cases": null
}
```

响应提供 `batch_id`、`total_cases` 和 `output_path`。

### 查询批次

`GET /api/v1/workflows/document-generation/batch/{batch_id}`

重点字段：

- 批次：`status`、`total_cases`、`generated_cases`、`completed_cases`、`needs_review_cases`、`failed_cases`
- 交付：`download_url`、`case_info_excel`
- 单案：`case_id`/`case_name`、`status`、`qa_report`、`missing_fields`、`documents`、`output_dir`

终态通常是 `completed`、`completed_with_errors` 或 `failed`。有文书产出的 `needs_review` 案件仍应下载并审计。

### 下载批次

`GET /api/v1/workflows/document-generation/batch/{batch_id}/download`

响应为 ZIP。客户端应使用流式写入、记录 SHA-256，并拒绝把路径解压到目标目录之外。

## 对照口径

| 优先级 | 来源 | 典型字段 | 规则 |
| --- | --- | --- | --- |
| 1 | `修改模板.xlsx` | 总租金、剩余本金、已付金额、买断价、到期买断价、违约金金额 | 金额字段优先覆盖生成数据 |
| 2 | 人工案件信息表 | 订单号、姓名、身份证、电话、法院、案由、设备、串码、合同/逾期日期 | 作为事实字段权威源 |
| 3 | 合同 OCR 原文 | 管辖约定、违约责任、租转售/买断条款 | 必须保留引用；不能只信 AI 摘要 |
| 4 | 规则计算 | 逾期天数、诉请合计、文书日期 | 按生成日期重算，记录计算公式 |

身份证号和手机号只在本地原始文件中保留；JSON/Markdown/DSH 消息中使用脱敏值。
