# -*- coding: utf-8 -*-
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import report_docx
from report_en import BLOCKS as EN
from report_zh import BLOCKS as ZH

OUT = os.path.dirname(HERE)

en = os.path.join(OUT, '论文精读报告-Understanding Real-World Concurrency Bugs in Go（英文）.docx')
zh = os.path.join(OUT, '论文精读报告-《理解Go语言真实世界中的并发缺陷》（中文）.docx')

print(report_docx.build(EN, en, 'en'))
print(report_docx.build(ZH, zh, 'zh'))
