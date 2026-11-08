---
name: idcard-merge-pdf
description: 将身份证正反面两张图片合并为单页 PDF 文档。当用户需要合并身份证正反面到一页 PDF、生成身份证扫描件、或者将多张身份证图片合并为一个 PDF 文件时触发此技能。支持调整正反面间距，保持原始比例，输出高分辨率 PDF。
---

# 身份证正反面合并 PDF

## 功能

将身份证正面和反面两张图片合并到一页 PDF 中，垂直排列，间距可调。

## 使用场景

- 上传身份证正反面图片，合并为单个 PDF 文件
- 调整正反面之间的间距（默认 5px，极小间距）
- 批量处理多张身份证

## 使用方法

### 命令行方式

```bash
python scripts/merge_idcard.py <正面图片> <反面图片> [-o 输出路径] [-g 间距]
```

参数：
- `front`：身份证正面图片路径
- `back`：身份证反面图片路径
- `-o, --output`：输出 PDF 路径，默认为 `idcard_merged.pdf`
- `-g, --gap`：正反面间距（像素），默认为 5

### 示例

```bash
# 基本用法
python scripts/merge_idcard.py front.jpg back.jpg

# 指定输出文件名
python scripts/merge_idcard.py front.jpg back.jpg -o my_idcard.pdf

# 调整间距为 10 像素
python scripts/merge_idcard.py front.jpg back.jpg -g 10
```

### Python API 方式

```python
from scripts.merge_idcard import merge_idcard_to_pdf

merge_idcard_to_pdf(
    front_path="front.jpg",
    back_path="back.jpg",
    output_path="output.pdf",
    gap_px=5
)
```

## 处理逻辑

1. 读取两张图片并统一转换为 RGB 模式
2. 以最大宽度为基准，等比例缩放两张图片（保持相同宽度）
3. 创建新画布，高度 = 正面高度 + 间距 + 反面高度
4. 垂直排列：正面上方，反面下方
5. 输出为 300 DPI 的 PDF 文件

## 依赖

- Python 3.7+
- Pillow (`pip install Pillow`)
