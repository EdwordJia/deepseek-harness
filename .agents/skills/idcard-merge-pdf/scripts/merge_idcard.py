"""
身份证正反面合并为单页 PDF

将身份证正面和反面两张图片合并到一页 PDF 中，垂直排列，间距极小。
"""

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("错误：需要 Pillow 库。请运行: pip install Pillow")
    sys.exit(1)


def merge_idcard_to_pdf(front_path: str, back_path: str, output_path: str, gap_px: int = 5):
    """
    将身份证正反面图片合并为一页 PDF。

    Args:
        front_path: 身份证正面图片路径
        back_path: 身份证反面图片路径
        output_path: 输出 PDF 路径
        gap_px: 正反面之间的间距（像素），默认 5
    """
    front = Image.open(front_path).convert("RGB")
    back = Image.open(back_path).convert("RGB")

    # 统一宽度（取两者最大宽度，但通常身份证正反面尺寸一致）
    target_width = max(front.width, back.width)

    # 按统一宽度等比例缩放
    def resize_to_width(img, width):
        if img.width == width:
            return img
        ratio = width / img.width
        new_height = int(img.height * ratio)
        return img.resize((width, new_height), Image.Resampling.LANCZOS)

    front = resize_to_width(front, target_width)
    back = resize_to_width(back, target_width)

    # 创建新画布：宽度 = target_width，高度 = 两张图高度 + 间隙
    total_height = front.height + gap_px + back.height
    merged = Image.new("RGB", (target_width, total_height), (255, 255, 255))

    # 粘贴正面（顶部）
    merged.paste(front, (0, 0))

    # 粘贴反面（正面下方 + 间隙）
    merged.paste(back, (0, front.height + gap_px))

    # 保存为 PDF
    merged.save(output_path, "PDF", resolution=300.0)
    print(f"已生成 PDF: {output_path}")
    print(f"  尺寸: {target_width} x {total_height} px")
    print(f"  正面: {front.width} x {front.height} px")
    print(f"  反面: {back.width} x {back.height} px")
    print(f"  间距: {gap_px} px")


def main():
    parser = argparse.ArgumentParser(description="身份证正反面合并为单页 PDF")
    parser.add_argument("front", help="身份证正面图片路径")
    parser.add_argument("back", help="身份证反面图片路径")
    parser.add_argument("-o", "--output", default="idcard_merged.pdf", help="输出 PDF 路径")
    parser.add_argument("-g", "--gap", type=int, default=5, help="正反面间距（像素），默认 5")

    args = parser.parse_args()

    # 检查文件是否存在
    for p in [args.front, args.back]:
        if not Path(p).exists():
            print(f"错误：文件不存在: {p}")
            sys.exit(1)

    merge_idcard_to_pdf(args.front, args.back, args.output, args.gap)


if __name__ == "__main__":
    main()
