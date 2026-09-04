"""Small dependency-free XLSX exporter for the public demo."""
from __future__ import annotations

import html
import io
import zipfile
from typing import Any


def _cell(value: Any) -> str:
    text = html.escape(str(value if value is not None else ""), quote=True)
    return f'<c t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet(rows: list[list[Any]], widths: list[int]) -> str:
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{width}" customWidth="1"/>' for i, width in enumerate(widths))
    body = []
    for row_no, row in enumerate(rows, 1):
        style = ' s="1"' if row_no == 1 else ''
        body.append(f'<row r="{row_no}">' + "".join(_cell(v) for v in row) + "</row>")
    max_col = chr(64 + min(max(len(row) for row in rows), 26)) if rows else "A"
    max_row = len(rows)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:{max_col}{max_row}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols>{cols}</cols><sheetData>{"".join(body)}</sheetData><autoFilter ref="A1:{max_col}{max_row}"/></worksheet>'''


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _script_rows(script: dict[str, Any], report: dict[str, Any]) -> list[list[Any]]:
    headers = ["镜头", "时间轴", "画面参考", "景别", "机位", "构图", "标准画面指导", "画面证据", "商品动作", "口播", "字幕", "销售阶段", "音效", "音乐", "剪辑", "素材", "合规提醒"]
    rows = [headers]
    source = script.get("shots") if isinstance(script.get("shots"), list) else []
    for shot in source:
        rows.append([
            shot.get("shot_id", ""), shot.get("time_range", ""), shot.get("reference_frame_url", ""), shot.get("shot_type", "未识别"),
            shot.get("camera_angle", "未识别"), shot.get("composition", "未识别"), shot.get("visual_scene", "未识别"), shot.get("visual_evidence", "未识别"),
            shot.get("product_appearance", "未识别") + "；" + shot.get("action", "未识别"), shot.get("voiceover", "未识别"), shot.get("subtitle", "未识别"),
            shot.get("sales_stage", "未识别"), shot.get("sound_effect", "未识别"), shot.get("music", "未识别"), shot.get("editing", "未识别"),
            "；".join(str(x) for x in _list(shot.get("materials"))), shot.get("compliance_note", "未识别"),
        ])
    if len(rows) == 1:
        for shot in report.get("shots", []):
            rows.append([shot.get("shot_id"), shot.get("time_range"), shot.get("screenshot_url"), shot.get("shot_size"), "手机固定机位", "主体与商品同框", shot.get("replication_advice"), "使用真实商品证据", shot.get("product_action"), "待补充", shot.get("subtitle_text"), shot.get("sales_stage"), "环境音", "低音量音乐", "按时间轴剪辑", "商品实拍素材", "不要虚构功效"])
    return rows


def _checklist_rows(script: dict[str, Any], report: dict[str, Any]) -> list[list[Any]]:
    rows = [["类别", "检查项目", "拍摄前具体准备", "优先级", "完成状态", "备注"]]
    items = [
        ("设备", "手机/相机", "确认电量、存储空间、画质和竖屏比例", "必须", "待确认", "建议统一使用同一设备"),
        ("设备", "支架/稳定器", "固定机位，保证前后对比画面角度一致", "必须", "待确认", "没有支架时使用稳定平面"),
        ("设备", "补光/自然光", "检查脸部、商品细节和材质是否清楚", "建议", "待确认", "避免商品反光过曝"),
        ("设备", "收音设备", "检查口播音量、环境噪声和麦克风电量", "建议", "待确认", "口播不清会影响转化"),
        ("画面", "前三秒画面", "准备价格/产品名/目标人群痛点的画面和动作", "必须", "待确认", "第一镜不要先做长自我介绍"),
        ("画面", "商品细节", "准备材质、结构、尺寸、功能区域的近景", "必须", "待确认", "每个卖点尽量配一个动作证据"),
        ("画面", "效果或使用证明", "准备真实对比、试用、拉扯、行走或场景测试", "必须", "待确认", "不要使用无法证明的夸张效果"),
        ("画面", "结尾CTA", "准备搜索词、商品页、价格或购买提示画面", "必须", "待确认", "价格与优惠需以实际信息为准"),
        ("天气/光线", "天气与外景", "如果有户外镜头，确认天气、风力、光线和备用室内场景", "视场景", "待确认", "室内拍摄可填写不适用"),
        ("服装搭配", "出镜服装", "准备与商品颜色、场景和账号人设匹配的主服装", "必须", "待确认", "避免图案过多抢商品主体"),
        ("服装搭配", "搭配单品", "鞋子、包、首饰、内搭等需要提前列出", "建议", "待确认", "保持不同镜头搭配连续"),
        ("商品道具", "商品本体", "确认商品、包装、尺码、颜色和备用件齐全", "必须", "待确认", "商品图片不能替代真实使用证明"),
        ("商品道具", "辅助道具", "准备衣架、尺子、对比商品、桌面或使用场景道具", "视脚本", "待确认", "按逐镜头脚本逐项核对"),
        ("声音剪辑", "背景音乐/音效", "选择不压住口播的音乐和轻量转场音效", "建议", "待确认", "确认音乐使用权限"),
        ("合规检查", "卖点与功效", "确认所有口播都来自真实商品信息或真实体验", "必须", "待确认", "不虚构、不夸大、不承诺爆单"),
    ]
    for item in items:
        rows.append(list(item))
    return rows


def _strategy_rows(script: dict[str, Any], report: dict[str, Any]) -> list[list[Any]]:
    p = script.get("product_understanding", {}) if isinstance(script.get("product_understanding"), dict) else {}
    return [
        ["项目", "内容"],
        ["商品可见信息", p.get("visible_information", "待确认")],
        ["待确认信息", "；".join(str(x) for x in _list(p.get("unknown_information")))],
        ["复刻策略", script.get("adaptation_strategy", "保留参考视频销售结构，替换为用户商品真实画面")],
        ["参考报告", report.get("report_id", "")],
        ["商品链接", script.get("product_image_url", "")],
        ["素材清单", "；".join(str(x) for x in _list(script.get("materials_checklist")))],
    ]


def build_script_xlsx(script: dict[str, Any], report: dict[str, Any]) -> bytes:
    sheets = [
        ("逐镜头脚本", _script_rows(script, report), [10, 14, 34, 12, 24, 24, 42, 36, 36, 40, 30, 14, 20, 18, 30, 34, 28]),
        ("拍摄前清单", _checklist_rows(script, report), [16, 24, 48, 12, 14, 36]),
        ("商品策略", _strategy_rows(script, report), [20, 90]),
    ]
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">', '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>', '<Default Extension="xml" ContentType="application/xml"/>', '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>', '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for i in range(1, len(sheets) + 1):
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    content_types.append('</Types>')
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join(f'<sheet name="{html.escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, (name, _, _) in enumerate(sheets, 1)) + '</sheets></workbook>'
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    workbook_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1)) + '<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><sz val="11"/><name val="Microsoft YaHei"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="E9E6FF"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0"/></cellXfs></styleSheet>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", ''.join(content_types))
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles)
        for i, (_, rows, widths) in enumerate(sheets, 1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", _sheet(rows, widths))
    return output.getvalue()
