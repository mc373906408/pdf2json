import clr
import sys
import os

sys.path.append(os.path.join(os.getcwd(), '3rd'))

clr.AddReference("Ppt2pdf")
from Ppt2pdf import Ppt2pdfClass


class Pynet:
    """python调用.net
    """

    def __init__(self):
        self.m_Ppt2pdfClass=Ppt2pdfClass()
        
    def pptCompatibilityFix(self,pptPath)->bool:
        return self.m_Ppt2pdfClass.pptCompatibilityFix(pptPath)

    def ppt2pdfCom(self,pptPath,pdfPath)->bool:
        # pdfPath 必须要\\表示目录，否则失败
        return self.m_Ppt2pdfClass.ppt2pdfCom(pptPath,pdfPath)
