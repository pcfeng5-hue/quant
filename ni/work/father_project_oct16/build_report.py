from pathlib import Path
import json
from xml.sax.saxutils import escape

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from pypdf import PdfReader

ROOT = Path('/Users/puchun/Documents/Codex/2026-10-07/ni')
OUT = ROOT / 'output/pdf'
OUT.mkdir(parents=True, exist_ok=True)
PDF = OUT / 'A股概率预测项目说明_家人阅读版_20261016.pdf'
MD = ROOT / 'outputs/A股概率预测项目说明_家人阅读版_20261016.md'

PAGES = [
    {
        'title': '我的出发点与核心想法',
        'subtitle': '把交易经验逐步变成有历史数据支持的概率判断',
        'blocks': [
            ('callout', '爸爸，我想建立一套自己使用的股票概率分析工具。把历史走势、筹码、成交和市场背景放在一起研究，找出哪些条件更值得买入、哪些时候应该等待，以及什么时候继续持有已经不划算。'),
            ('h', '我为什么会有这个想法'),
            ('p', '做股票约两年以后，我越来越想弄清楚：很多时候，我觉得价格跌得差不多了，或者认为一段上涨还会继续，这些判断到底有多少历史依据？如果能把过去类似情况完整统计出来，我就能更清楚地区分“觉得有机会”和“有证据支持的机会”。'),
            ('p', '所以，我想把自己的观察和数据研究结合起来。先看上涨、下跌和震荡之前出现过什么变化，再检查这些变化在新行情中是否仍有参考价值，逐步形成自己的买卖判断体系。'),
            ('h', '我希望它帮我回答四个问题'),
            ('table', [['我的问题', '希望获得的依据'], ['这次回落值得买吗？', '类似条件下，未来一定期限内上涨与扣费后盈利的概率。'], ['是不是还应该再等？', '多等几个确认条件，能减少多少风险，又会错过多少机会。'], ['上涨以后还能拿多久？', '继续持有的收益空间、回落风险和支持证据。'], ['现在卖出是否更合适？', '卖出后持币与继续持有，在同一段时间内的结果比较。']], [126, 373]),
            ('h', '我想追求的使用价值'),
            ('p', '每次做决定时，我希望能看到：胜算有多大，可能赚亏多少，判断依据是什么，以及证据是否足够。条件不成熟就继续观察，少赚一点也可以，尽量减少只凭相对价格或怕错过而做的决定。'),
            ('note', '我希望把它逐步培养成自己的概率预测工具：持续研究、持续记录、持续验证，用来辅助我独立判断。')
        ]
    },
    {
        'title': '我最想研究哪些关系',
        'subtitle': '重点看筹码、量价和信号组合如何对应后续走势',
        'blocks': [
            ('h', '先把少数股票研究透'),
            ('p', '我的想法是先从一只或少数几只股票开始，了解公司、行业和基本面，再把同一只股票不同时期的市场数据连起来观察。目前先以高德红外（002414.SZ）为第一个研究对象，整理2023年以来的数据。'),
            ('h', '筹码与股价，是我尤其重视的部分'),
            ('p', '我想研究：股价回落时，筹码成本区间怎样变化？筹码集中、分散、向上或向下迁移以后，后续走势有什么区别？价格突破某个成本区间时，成交量和换手有没有配合？这些变化能否帮助区分普通波动、较成熟的反转和仍然偏弱的行情？'),
            ('p', '这些先作为研究问题。供应商展示的筹码属于有口径和假设的估计，需要核对来源与历史一致性；不能直接当作某些机构的真实持仓。'),
            ('table', [['观察维度', '我想寻找的关系'], ['价格与趋势', '日K、回调幅度、相对位置，以及MA5/10/15的方向和排列。'], ['动量与拐点', 'MACD、KDJ转向与价格转向的先后关系，失败信号有哪些特征。'], ['成交与换手', '放量、缩量、换手变化，怎样与涨跌和筹码迁移相互配合。'], ['市场与事件', '行业、大盘、公司公告和新闻政策变化，是否改变同一信号的表现。']], [100, 399]),
            ('h', '把A股的市场环境放进来一起看'),
            ('p', '我希望把政策、新闻、已披露机构交易和大单分类作为背景信息，也记录股指期货交割、期权到期、除权除息与派息日期。先核对信息，再检验它们在哪些情况下有参考价值；日期出现本身不等于必然有大行情。'),
            ('note', '我最关心的是：多个变化同时出现时，后续上涨或下跌是否更有规律；这些信息能不能比单看价格提供更多帮助。')
        ]
    },
    {
        'title': '怎样把观察变成概率',
        'subtitle': '从单个信号到组合，再用后来发生的行情检验',
        'blocks': [
            ('flow', ['1 整理数据', '2 统计信号', '3 比较组合', '4 新行情验证', '5 小额检验']),
            ('h', '先把“上涨”和“下跌”说清楚'),
            ('p', '每次研究先确定观察多久、涨跌多少、按什么实际可成交价格计算，并把费用计入结果。然后统计：单个信号出现以后，上涨、横盘和下跌分别发生多少次，赚亏幅度如何，与当时市场本来的概率相比有没有改善。具体预测周期仍待确定。'),
            ('h', '再看几个信号组合以后有没有改善'),
            ('p', '例如，价格回落以后，如果筹码成本区间变化、量能变化和某些指标转向一起出现，后续结果是否比单一条件更好？哪些组合更常出现在上涨之前，哪些组合更容易对应下跌？这类问题需要直接统计组合结果，不能把单信号概率简单相加或相乘。'),
            ('p', '成功、失败、横盘和没有出现信号的时期都要保留。只挑涨得好的走势找共同点，很容易把偶然看成规律；我希望保留完整记录，明确一种方法在什么情况下也会失效。'),
            ('h', '买入与卖出各自寻找依据'),
            ('p', '买入时，重点比较“现在介入”和“再等确认”各有什么收益与代价。持仓以后，则重新评估继续上涨的空间、回落风险，以及继续持有与卖出持币的差异。卖出机会需要自己的证据，不能直接从买入概率反推。'),
            ('h', '最后要让概率经得起新行情检验'),
            ('p', '找到历史规律以后，先固定规则，再用没有参与调整的新行情检验。还要看系统报出的概率是否可信：某一概率区间的预测，在后续样本中的实际发生频率是否接近。样本不足或市场环境变了，就降低信任或继续观察。[1]'),
            ('note', '我希望最终看到的是一张清楚的判断卡：当前条件、上涨与下跌概率、可能赚亏多少、中途风险、证据可靠程度，以及买入、等待、持有或卖出的比较。')
        ]
    },
    {
        'title': '目前做到哪里，接下来怎么走',
        'subtitle': '截至2026年10月16日，先完成研究，再逐步检验实际价值',
        'blocks': [
            ('h', '目前已经做了什么'),
            ('p', '已整理项目目标、风险意向、分阶段路线图及概率研究详细规格。数据库上一核查快照包含高德红外2023年1月3日至2026年10月15日的914个日线日期，并对价格、成交量做了跨来源核对；还整理了公司公告、财务和部分事件证据。914个日期不代表914次独立交易。'),
            ('p', '东方财富网页已验证两日历史筹码摘要可随日期变化，但完整历史筹码档位仍未取得；新闻、历史证券状态、信息可得时间及部分来源口径仍有缺口。目前仍是数据核对和设计阶段，尚未计算技术指标或涨跌概率，没有经过验证的模型收益结论。'),
            ('table', [['阶段', '我希望完成的事情'], ['短期：未来2至4周目标', '明确第一轮预测问题，列清可用数据与缺口，优先继续核验筹码及关键数据。'], ['中期：约2至6个月目标', '完成单信号、有限组合及新行情验证；有可靠候选以后，用逐日记录和模拟观察检验。'], ['长期：约6至12个月目标', '条件通过后评审1万元小额试验，核对真实收益、成本和风险，逐步完善自己的概率判断体系。']], [126, 373]),
            ('p', '这些是方向性目标；数据、独立样本或验证不够就延后。研究中允许出现“没有发现可靠优势”的结果，不能为了赶进度硬选一种方法。'),
            ('h', '资金和基本纪律'),
            ('p', '最初考虑为项目准备5万元，目前最新意向是条件成熟后先用1万元检验，原总体资金意向是否调整尚未明确。试验阶段累计已实现亏损达到2,000元时，暂停新增买入并复核；浮亏不计入这条线，因此它不是账户最大亏损保证。净值、单笔风险和仓位保护还需补齐。'),
            ('p', '我已明确不碰ST，允许空仓，不为额外利润临时放宽风险计划。数据和软件每月费用上限约2,000元，按需要控制支出，并把费用计入项目总结果。'),
            ('h', '怎样把想法继续做下去'),
            ('p', '我提供交易观察、想研究的问题和风险偏好；用AI辅助编程、整理数据和统计，把这些想法逐项落实为可以复查的研究。最后由我结合证据作出判断，并记录实际结果，持续检查这套方法有没有帮助。'),
            ('source', '方法参考：[1] scikit-learn官方概率校准说明：https://scikit-learn.org/stable/modules/calibration.html 。'),
            ('source', '项目状态依据：本地《概率预测引擎详细方案》《项目进度与交易需求档案》及2026年10月15日数据库核查记录。本文为项目说明，不包含实测预测或收益承诺。')
        ]
    }
]

pdfmetrics.registerFont(TTFont('Chinese', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
pdfmetrics.registerFontFamily('Chinese', normal='Chinese', bold='Chinese', italic='Chinese', boldItalic='Chinese')
NAVY = colors.HexColor('#152C43')
TEAL = colors.HexColor('#147D86')
INK = colors.HexColor('#253645')
MUTED = colors.HexColor('#647487')
PALE = colors.HexColor('#EFF6F7')
LINE = colors.HexColor('#D8E1E9')

styles = {
    'title': ParagraphStyle('TitleCN', fontName='Chinese', fontSize=24, leading=32, textColor=NAVY, spaceAfter=7, wordWrap='CJK'),
    'subtitle': ParagraphStyle('SubtitleCN', fontName='Chinese', fontSize=10.8, leading=17, textColor=MUTED, spaceAfter=16, wordWrap='CJK'),
    'h': ParagraphStyle('HeadingCN', fontName='Chinese', fontSize=13.4, leading=20, textColor=TEAL, spaceBefore=9, spaceAfter=6, keepWithNext=True, wordWrap='CJK'),
    'p': ParagraphStyle('BodyCN', fontName='Chinese', fontSize=10.5, leading=17.2, textColor=INK, spaceAfter=8, wordWrap='CJK'),
    'table': ParagraphStyle('TableCN', fontName='Chinese', fontSize=10.1, leading=16, textColor=INK, wordWrap='CJK'),
    'th': ParagraphStyle('TableHeaderCN', fontName='Chinese', fontSize=10.3, leading=16, textColor=colors.white, wordWrap='CJK'),
    'note': ParagraphStyle('NoteCN', fontName='Chinese', fontSize=10.1, leading=16.7, textColor=NAVY, spaceAfter=0, wordWrap='CJK'),
    'source': ParagraphStyle('SourceCN', fontName='Chinese', fontSize=7.5, leading=11, textColor=MUTED, spaceAfter=5, wordWrap='CJK'),
    'flow': ParagraphStyle('FlowCN', fontName='Chinese', fontSize=9.2, leading=15, textColor=TEAL, alignment=1, wordWrap='CJK'),
}

def para(text, style='p'):
    return Paragraph(escape(text), styles[style])

def card(text):
    tab = Table([[para(text, 'note')]], colWidths=[499])
    tab.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PALE),
        ('BOX', (0, 0), (-1, -1), 0.5, LINE),
        ('LINEBEFORE', (0, 0), (0, -1), 3, TEAL),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    return tab

def make_table(rows, widths):
    content = [[para(cell, 'th' if i == 0 else 'table') for cell in row] for i, row in enumerate(rows)]
    t = Table(content, colWidths=widths, hAlign='LEFT', repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F5F8FA'), colors.white]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    return t

def decoration(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(TEAL)
    canvas.rect(0, h-8, w, 8, stroke=0, fill=1)
    canvas.setFont('Chinese', 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(48, h-34, 'A股概率预测与交易辅助项目 / 家人阅读版')
    canvas.setStrokeColor(LINE)
    canvas.line(48, 41, w-48, 41)
    canvas.drawString(48, 26, '2026/10/16  |  当前处于数据核对与研究设计阶段')
    canvas.drawRightString(w-48, 26, f'{doc.page}')
    canvas.restoreState()

story = []
markdown = ['# A股概率预测与交易辅助项目说明', '', '家人阅读版 | 2026年10月16日 | 当前处于数据核对与研究设计阶段', '']
for index, page in enumerate(PAGES):
    if index:
        story.append(PageBreak())
    story.extend([para(f'{index+1:02d}  {page["title"]}', 'title'), para(page['subtitle'], 'subtitle')])
    markdown.extend([f'## {index+1}. {page["title"]}', '', page['subtitle'], ''])
    for block in page['blocks']:
        kind = block[0]
        if kind == 'h':
            story.append(para(block[1], 'h'))
            markdown.extend([f'### {block[1]}', ''])
        elif kind in ['p', 'source']:
            story.append(para(block[1], kind))
            markdown.extend([block[1], ''])
        elif kind in ['callout', 'note']:
            story.extend([card(block[1]), Spacer(1, 9)])
            markdown.extend([f'> {block[1]}', ''])
        elif kind == 'table':
            story.extend([make_table(block[1], block[2]), Spacer(1, 10)])
            for i, row in enumerate(block[1]):
                markdown.append('| ' + ' | '.join(row) + ' |')
                if i == 0:
                    markdown.append('|' + '|'.join(['---'] * len(row)) + '|')
            markdown.append('')
        elif kind == 'flow':
            t = Table([[para(x, 'flow') for x in block[1]]], colWidths=[99.8]*5)
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),0.4,LINE),('INNERGRID',(0,0),(-1,-1),0.4,LINE),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
            story.extend([t, Spacer(1, 9)])
            markdown.extend([' → '.join(block[1]), ''])

MD.write_text('\n'.join(markdown), encoding='utf-8')
doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=48, rightMargin=48,
                        topMargin=53, bottomMargin=55, title='A股概率预测与交易辅助项目说明',
                        author='项目研究记录', subject='家人阅读版，2026年10月16日')
doc.build(story, onFirstPage=decoration, onLaterPages=decoration)
reader = PdfReader(str(PDF))
summary = {'pdf':str(PDF), 'markdown':str(MD), 'pages':len(reader.pages),
           'page_text_lengths':[len(p.extract_text() or '') for p in reader.pages],
           'pdf_bytes':PDF.stat().st_size}
(ROOT / 'work/father_project_oct16/build_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(summary, ensure_ascii=False, indent=2))
