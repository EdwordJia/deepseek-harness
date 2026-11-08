"""
OCR 智能文件命名工具

支持图片和 PDF 的 OCR 识别，并根据识别内容自动重命名文件。
命名规则：从文档中提取人名、日期、文件类型等关键信息，生成规范文件名。

参考命名格式：2026-07-陈嘉鑫.zip
"""

import argparse
import base64
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

try:
    import fitz
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("警告: 未安装 PyMuPDF，PDF 支持不可用。请运行: pip install PyMuPDF")

try:
    from PIL import Image
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False
    print("警告: 未安装 Pillow，图片处理不可用。请运行: pip install Pillow")


# API 配置
OCR_API_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
MAX_FILE_SIZE = 20 * 1024 * 1024


def _load_token() -> Optional[str]:
    """Read the PaddleOCR token from the environment or the private DSH config file."""
    token = os.getenv("PADDLEOCR_API_TOKEN")
    if token and token.strip():
        return token.strip()
    private = Path.home() / ".dsh" / "paddleocr.token"
    if private.is_file():
        value = private.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None

# 支持的文件格式
SUPPORTED_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.tif'}
SUPPORTED_PDF_EXTS = {'.pdf'}
SUPPORTED_EXTS = SUPPORTED_IMAGE_EXTS | SUPPORTED_PDF_EXTS


class OcrClient:
    """OCR 客户端"""

    def __init__(self, token: Optional[str] = None):
        resolved = token or _load_token()
        if not resolved:
            raise RuntimeError(
                "未配置 PaddleOCR token：请设置 PADDLEOCR_API_TOKEN 环境变量，"
                "或把 token 写入 ~/.dsh/paddleocr.token"
            )
        self.token = resolved
        self.headers = {"Authorization": f"bearer {self.token}"}

    def _submit_job(self, file_data: bytes, filename: str, is_pdf: bool = False) -> Optional[str]:
        """提交 OCR 任务"""
        payload = {
            "useDocOrientationClassify": True,
            "useDocUnwarping": True,
            "useChartRecognition": False,
            "useOcrForImageBlock": True,
        }

        data = {
            "model": "PaddleOCR-VL-1.6",
            "optionalPayload": json.dumps(payload),
        }

        files = {
            "file": (filename, io.BytesIO(file_data))
        }

        try:
            response = requests.post(
                OCR_API_URL,
                headers=self.headers,
                data=data,
                files=files,
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                job_id = result.get("data", {}).get("jobId")
                print(f"  任务已提交: {job_id}")
                return job_id
            else:
                print(f"  提交失败: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            print(f"  提交异常: {e}")
            return None

    def _poll_result(self, job_id: str, max_wait: int = 300) -> Optional[str]:
        """轮询获取 OCR 结果"""
        import time
        start = time.time()
        while time.time() - start < max_wait:
            try:
                response = requests.get(
                    f"{OCR_API_URL}/{job_id}",
                    headers=self.headers,
                    timeout=10
                )
                if response.status_code == 200:
                    result = response.json()
                    state = result.get("data", {}).get("state")
                    if state == "done":
                        return result.get("data", {}).get("resultUrl", {}).get("jsonUrl")
                    elif state == "failed":
                        print(f"  任务失败: {result.get('data', {}).get('errorMsg')}")
                        return None
            except Exception as e:
                print(f"  查询异常: {e}")
            time.sleep(5)
        print("  任务超时")
        return None

    def _download_result(self, jsonl_url: str) -> str:
        """下载 OCR 结果"""
        try:
            # The BOS signed URL carries its own authorization query; sending the OCR
            # bearer header as well makes BOS answer 400.
            response = requests.get(jsonl_url, timeout=30)
            response.raise_for_status()
            content = response.text

            texts = []
            for line in content.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                    for block in parsed.get("result", {}).get("layoutParsingResults", []):
                        txt = block.get("markdown", {}).get("text", "")
                        if txt:
                            texts.append(txt)
                except Exception:
                    continue
            return "\n\n".join(texts)
        except Exception as e:
            print(f"  下载结果失败: {e}")
            return ""

    def recognize(self, file_path: str) -> str:
        """识别文件内容"""
        path = Path(file_path)
        print(f"正在识别: {path.name}")

        # 检查文件大小
        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            print(f"  文件过大: {file_size / 1024 / 1024:.1f}MB (最大 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB)")
            return ""

        # 读取文件
        with open(path, "rb") as f:
            file_data = f.read()

        is_pdf = path.suffix.lower() in SUPPORTED_PDF_EXTS

        if is_pdf and PDF_SUPPORT:
            return self._recognize_pdf(file_path)
        else:
            job_id = self._submit_job(file_data, path.name, is_pdf)
            if not job_id:
                return ""
            jsonl_url = self._poll_result(job_id)
            if not jsonl_url:
                return ""
            return self._download_result(jsonl_url)

    def _recognize_pdf(self, pdf_path: str) -> str:
        """识别 PDF 内容（逐页处理）"""
        doc = fitz.open(pdf_path)
        all_text = []

        for page_num in range(len(doc)):
            print(f"  处理第 {page_num + 1}/{len(doc)} 页...")
            page = doc[page_num]

            # 转换为高清图片
            zoom = 300 / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")

            # 分割长图片
            img = Image.open(io.BytesIO(img_bytes))
            width, height = img.size

            parts = []
            if height > 3000:
                y = 0
                while y < height:
                    end_y = min(y + 3000, height)
                    cropped = img.crop((0, y, width, end_y))
                    buffer = io.BytesIO()
                    cropped.save(buffer, format="PNG")
                    parts.append(buffer.getvalue())
                    y = end_y - 100 if end_y < height else height
            else:
                parts = [img_bytes]

            for part in parts:
                job_id = self._submit_job(part, f"page_{page_num + 1}.png")
                if not job_id:
                    continue
                jsonl_url = self._poll_result(job_id)
                if not jsonl_url:
                    continue
                text = self._download_result(jsonl_url)
                if text:
                    all_text.append(text)

        doc.close()
        return "\n\n".join(all_text)


class FileNamingExtractor:
    """从 OCR 文本中提取命名信息"""

    # 常见的姓名关键词
    NAME_KEYWORDS = ['姓名', '申请人', '借款人', '出租人', '承租人', '客户', '用户', '本人',
                     '经办人', '联系人', '负责人', '代表人', '代理人', '甲方', '乙方']

    # 常见的日期格式
    DATE_PATTERNS = [
        r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',
        r'(\d{4})-(\d{2})-(\d{2})',
        r'(\d{4})/(\d{2})/(\d{2})',
        r'(\d{4})\.(\d{2})\.(\d{2})',
        r'(\d{4})(\d{2})(\d{2})',
    ]

    # 文件类型关键词
    DOC_TYPE_KEYWORDS = {
        '身份证': ['身份证', '身份證', 'ID card'],
        '合同': ['合同', '协议', '契约', '合約'],
        '账单': ['账单', '明细', '对账单', '还款', '扣款'],
        '报告': ['报告', '分析报告', '评估报告'],
        '申请表': ['申请', '申请表', '申请书'],
        '发票': ['发票', '收据', '凭证'],
        '证明': ['证明', '证书', '公证书'],
        '截图': ['截图', '截屏', '屏幕截图'],
    }

    def __init__(self, text: str):
        self.text = text

    def extract_name(self) -> Optional[str]:
        """提取人名"""
        # 方法1: 通过关键词匹配
        for keyword in self.NAME_KEYWORDS:
            pattern = rf'{keyword}[\s:：]+([\u4e00-\u9fa5]{{2,4}})'
            match = re.search(pattern, self.text)
            if match:
                name = match.group(1)
                # 验证姓名长度和合理性
                if 2 <= len(name) <= 4:
                    return name

        # 方法2: 查找中文姓名模式（常见姓氏）
        common_surnames = ['张', '王', '李', '刘', '陈', '杨', '黄', '赵', '周', '吴',
                          '徐', '孙', '马', '朱', '胡', '郭', '何', '高', '林', '罗',
                          '郑', '梁', '谢', '宋', '唐', '许', '韩', '冯', '邓', '曹',
                          '彭', '曾', '肖', '田', '董', '袁', '潘', '于', '蒋', '蔡',
                          '余', '杜', '叶', '程', '苏', '魏', '吕', '丁', '任', '沈',
                          '姚', '卢', '姜', '崔', '钟', '谭', '陆', '汪', '范', '金',
                          '石', '廖', '贾', '夏', '韦', '付', '方', '白', '邹', '孟',
                          '熊', '秦', '邱', '江', '尹', '薛', '闫', '段', '雷', '侯',
                          '龙', '史', '陶', '黎', '贺', '顾', '毛', '郝', '龚', '邵',
                          '万', '钱', '严', '覃', '武', '戴', '莫', '孔', '向', '汤']

        for surname in common_surnames:
            pattern = rf'{surname}[\u4e00-\u9fa5]{{1,3}}(?:[\s\n]|$)'
            matches = re.findall(pattern, self.text)
            for match in matches:
                name = match.strip()
                if 2 <= len(name) <= 4:
                    return name

        return None

    def extract_date(self) -> Optional[Tuple[int, int, int]]:
        """提取日期，返回 (年, 月, 日)"""
        # 排除关键词：出生日期不是我们想要的
        EXCLUDE_KEYWORDS = ['出生', '生于', '出生日期']
        PRIORITY_KEYWORDS = ['有效期限', '签发', '签署', '签订', '日期', '账单周期', '还款日期']

        # 先找到所有日期及其位置
        all_dates = []
        for pattern in self.DATE_PATTERNS:
            for match in re.finditer(pattern, self.text):
                groups = match.groups()
                if len(groups) == 3:
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                        all_dates.append({
                            'date': (year, month, day),
                            'pos': match.start(),
                            'text': match.group()
                        })

        if not all_dates:
            return None

        # 检查日期附近的关键词，优先选择有业务意义的日期
        scored_dates = []
        for item in all_dates:
            pos = item['pos']
            # 获取日期前后的上下文（50个字符）
            context_start = max(0, pos - 50)
            context_end = min(len(self.text), pos + 50)
            context = self.text[context_start:context_end]

            # 检查是否包含排除关键词
            excluded = any(kw in context for kw in EXCLUDE_KEYWORDS)
            if excluded:
                continue

            # 检查是否包含优先关键词
            priority = any(kw in context for kw in PRIORITY_KEYWORDS)

            scored_dates.append({
                'date': item['date'],
                'priority': priority,
                'pos': pos
            })

        if not scored_dates:
            # 如果都被排除了，返回第一个合理的日期
            return all_dates[0]['date']

        # 优先选择有优先关键词的日期，然后按位置排序
        scored_dates.sort(key=lambda x: (not x['priority'], x['pos']))
        return scored_dates[0]['date']

    def extract_doc_type(self) -> Optional[str]:
        """提取文档类型"""
        for doc_type, keywords in self.DOC_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in self.text:
                    return doc_type
        return None

    def extract_info(self) -> Dict[str, Optional[str]]:
        """提取所有信息"""
        name = self.extract_name()
        date = self.extract_date()
        doc_type = self.extract_doc_type()

        result = {
            'name': name,
            'date': f"{date[0]}-{date[1]:02d}" if date else None,
            'full_date': f"{date[0]}-{date[1]:02d}-{date[2]:02d}" if date else None,
            'doc_type': doc_type,
            'year': str(date[0]) if date else None,
            'month': f"{date[1]:02d}" if date else None,
        }

        return result


def generate_filename(extracted_info: Dict, original_path: str, naming_pattern: str = "{date}-{name}") -> str:
    """
    根据提取信息生成新文件名

    Args:
        extracted_info: 提取的信息字典
        original_path: 原始文件路径
        naming_pattern: 命名模板，可用变量: {date}, {name}, {doc_type}, {year}, {month}
    """
    path = Path(original_path)
    ext = path.suffix

    # 如果没有提取到日期，使用当前日期
    date = extracted_info.get('date') or datetime.now().strftime("%Y-%m")
    name = extracted_info.get('name') or "未知"
    doc_type = extracted_info.get('doc_type') or "文档"
    year = extracted_info.get('year') or datetime.now().strftime("%Y")
    month = extracted_info.get('month') or datetime.now().strftime("%m")

    # 替换模板变量
    filename = naming_pattern.format(
        date=date,
        name=name,
        doc_type=doc_type,
        year=year,
        month=month
    )

    # 清理文件名中的非法字符
    filename = re.sub(r'[<>"/\\|?*]', '_', filename)
    filename = filename.strip()

    return f"{filename}{ext}"


def process_file(file_path: str, naming_pattern: str = "{date}-{name}", output_dir: Optional[str] = None,
                 dry_run: bool = False) -> Tuple[str, str]:
    """
    处理单个文件：OCR 识别 + 重命名

    Args:
        file_path: 文件路径
        naming_pattern: 命名模板
        output_dir: 输出目录，None 则使用原目录
        dry_run: 是否仅预览，不实际重命名

    Returns:
        (原始文件名, 新文件名)
    """
    path = Path(file_path)
    if not path.exists():
        print(f"文件不存在: {file_path}")
        return (path.name, "")

    if path.suffix.lower() not in SUPPORTED_EXTS:
        print(f"不支持的格式: {path.suffix}")
        return (path.name, "")

    # OCR 识别
    print(f"\n{'='*60}")
    print(f"处理文件: {path.name}")
    print(f"{'='*60}")

    client = OcrClient()
    text = client.recognize(file_path)

    if not text:
        print("  未能识别到文本内容")
        return (path.name, "")

    print(f"  识别文本长度: {len(text)} 字符")
    print(f"  文本预览: {text[:200]}...")

    # 提取信息
    extractor = FileNamingExtractor(text)
    info = extractor.extract_info()

    print(f"\n  提取信息:")
    for key, value in info.items():
        if value:
            print(f"    {key}: {value}")

    # 生成新文件名
    new_filename = generate_filename(info, file_path, naming_pattern)

    # 确定输出路径
    if output_dir:
        output_path = Path(output_dir) / new_filename
    else:
        output_path = path.parent / new_filename

    print(f"\n  重命名: {path.name}")
    print(f"  新名称: {new_filename}")
    print(f"  输出路径: {output_path}")

    if not dry_run:
        # 如果目标文件已存在，添加序号
        if output_path.exists():
            stem = output_path.stem
            suffix = output_path.suffix
            counter = 1
            while output_path.exists():
                output_path = output_path.with_name(f"{stem}_{counter}{suffix}")
                counter += 1

        try:
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                import shutil
                shutil.copy2(file_path, output_path)
                print(f"  已复制到: {output_path}")
            else:
                path.rename(output_path)
                print(f"  已重命名")
        except Exception as e:
            print(f"  重命名失败: {e}")
            return (path.name, "")
    else:
        print("  [预览模式] 未实际重命名")

    return (path.name, new_filename)


def process_directory(input_dir: str, naming_pattern: str = "{date}-{name}",
                      output_dir: Optional[str] = None, dry_run: bool = False,
                      recursive: bool = False) -> List[Tuple[str, str]]:
    """批量处理目录中的文件"""
    path = Path(input_dir)
    if not path.is_dir():
        print(f"不是目录: {input_dir}")
        return []

    if recursive:
        files = [f for f in path.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS]
    else:
        files = [f for f in path.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS]

    print(f"\n共发现 {len(files)} 个文件待处理")
    print(f"命名模板: {naming_pattern}")
    if output_dir:
        print(f"输出目录: {output_dir}")
    if dry_run:
        print("模式: 预览 (不实际重命名)")
    print()

    results = []
    for i, file_path in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] ")
        original, new_name = process_file(str(file_path), naming_pattern, output_dir, dry_run)
        results.append((original, new_name))

    return results


def main():
    parser = argparse.ArgumentParser(description="OCR 智能文件命名工具")
    parser.add_argument("input", help="输入文件或目录路径")
    parser.add_argument("-p", "--pattern", default="{date}-{name}",
                        help="命名模板，可用变量: {date}, {name}, {doc_type}, {year}, {month}")
    parser.add_argument("-o", "--output", help="输出目录（默认覆盖原文件）")
    parser.add_argument("-d", "--dry-run", action="store_true", help="预览模式，不实际重命名")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归处理子目录")
    parser.add_argument("--show-text", action="store_true", help="显示完整识别文本")

    args = parser.parse_args()

    input_path = Path(args.input)

    if input_path.is_file():
        original, new_name = process_file(
            str(input_path),
            naming_pattern=args.pattern,
            output_dir=args.output,
            dry_run=args.dry_run
        )
        if args.show_text and new_name:
            # 重新识别以显示文本
            client = OcrClient()
            text = client.recognize(str(input_path))
            print(f"\n{'='*60}")
            print("完整识别文本:")
            print(f"{'='*60}")
            print(text)
    elif input_path.is_dir():
        process_directory(
            str(input_path),
            naming_pattern=args.pattern,
            output_dir=args.output,
            dry_run=args.dry_run,
            recursive=args.recursive
        )
    else:
        print(f"路径不存在: {args.input}")


if __name__ == "__main__":
    main()
