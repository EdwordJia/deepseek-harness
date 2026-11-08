---
name: ocr-auto-rename
description: 使用 OCR 识别文档内容并自动重命名文件。当用户需要识别图片/PDF 中的文字、根据文档内容提取人名/日期自动命名文件、批量整理扫描件、智能归档文档时触发此技能。支持身份证、合同、账单、申请表等常见文档类型的信息提取和命名。
---

# OCR 智能文件命名

## 功能

1. **OCR 识别**：使用 PaddleOCR API 识别图片和 PDF 文档中的文字内容
2. **信息提取**：从识别文本中提取人名、日期、文档类型等关键信息
3. **智能命名**：根据提取信息自动生成规范文件名，支持自定义命名模板

## 使用场景

- 扫描件归档：身份证、合同、账单等自动命名
- 批量整理：大量扫描文档按人名/日期分类重命名
- 微信文件整理：识别聊天中收到的文件内容并规范命名
- 文档数字化：将纸质文件扫描后自动提取信息命名

## 配置

PaddleOCR 需要访问令牌。优先读取环境变量 `PADDLEOCR_API_TOKEN`；未设置时读取私有文件 `~/.dsh/paddleocr.token`（权限 600）。令牌不要写进仓库。

```bash
export PADDLEOCR_API_TOKEN=<your-token>
# 或
printf '%s\n' '<your-token>' > ~/.dsh/paddleocr.token && chmod 600 ~/.dsh/paddleocr.token
```

## 使用方法

### 命令行

```bash
# 单文件处理
python scripts/ocr_rename.py <文件路径> -p "{date}-{name}"

# 批量处理目录
python scripts/ocr_rename.py <目录路径> -r -p "{date}-{name}"

# 预览模式（不实际重命名）
python scripts/ocr_rename.py <文件路径> -d

# 输出到指定目录
python scripts/ocr_rename.py <文件路径> -o "输出目录"

# 显示完整识别文本
python scripts/ocr_rename.py <文件路径> --show-text
```

### 参数说明

- `input`: 输入文件或目录路径
- `-p, --pattern`: 命名模板，可用变量：
  - `{date}`: 日期 (YYYY-MM)
  - `{name}`: 提取的人名
  - `{doc_type}`: 文档类型（身份证/合同/账单等）
  - `{year}`: 年份
  - `{month}`: 月份
- `-o, --output`: 输出目录（默认覆盖原文件）
- `-d, --dry-run`: 预览模式
- `-r, --recursive`: 递归处理子目录

### 命名示例

| 文档内容 | 模板 | 输出文件名 |
|---------|------|-----------|
| 身份证 姓名：陈嘉鑫 | `{date}-{name}` | `2026-07-陈嘉鑫.pdf` |
| 合同 甲方：张三 | `{name}-{doc_type}` | `张三-合同.pdf` |
| 账单 2026-01-15 | `{year}-{month}-{doc_type}` | `2026-01-账单.pdf` |

### Python API

```python
from scripts.ocr_rename import process_file, process_directory

# 单文件处理
original, new_name = process_file(
    file_path="document.pdf",
    naming_pattern="{date}-{name}",
    output_dir="output/",
    dry_run=False
)

# 批量处理
results = process_directory(
    input_dir="documents/",
    naming_pattern="{date}-{name}",
    output_dir="output/",
    dry_run=True,
    recursive=True
)
```

## 识别能力

### 支持格式
- **图片**: .png, .jpg, .jpeg, .bmp, .webp, .tiff, .tif
- **PDF**: .pdf (自动分页处理)

### 信息提取
- **人名**: 通过关键词（姓名、申请人、借款人等）或中文姓名模式识别
- **日期**: 支持多种格式（2024年1月1日、2024-01-01、2024/01/01 等）
- **文档类型**: 自动识别身份证、合同、账单、报告、申请表等

### 命名规则
- 自动清理文件名中的非法字符（<>"/\\|?*）
- 文件名冲突时自动添加序号（如：文件_1.pdf）
- 优先使用文档中的日期，无日期则使用当前日期
- 无姓名则使用"未知"作为占位符

## 依赖

- Python 3.8+
- requests (`pip install requests`)
- PyMuPDF (`pip install PyMuPDF`) - PDF 支持
- Pillow (`pip install Pillow`) - 图片处理

## 注意事项

- 需要网络连接以调用 PaddleOCR API
- 单文件大小限制 20MB
- 复杂表格或手写体识别准确率可能受限
- 建议先使用 `-d` 预览模式测试效果
