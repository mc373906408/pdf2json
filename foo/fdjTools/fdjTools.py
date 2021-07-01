from fractions import Fraction
from typing import List


class Tools:
    """工具类
    """

    def __init__(self):
        pass

    def isRectangleOverlap(self, rec1: List[int], rec2: List[int]):
        """判断矩形是否重叠
        """
        x_overlap = not(rec1[2] <= rec2[0] or rec2[2] <= rec1[0])
        y_overlap = not(rec1[3] <= rec2[1] or rec2[3] <= rec1[1])
        return x_overlap and y_overlap
    
    def isRectangleContainRectangle(self,rec1,rec2):
        """判断矩形rec1是否包含矩形rec2
        """
        return rec1[0]<=rec2[0] and rec2[2]<=rec1[2] and rec1[1]<=rec2[1] and rec2[3]<=rec1[3]
    
    def toIntBbox(self,bbox):
        intBbox=[]
        for floatBbox in bbox:
            intBbox.append(int(round(floatBbox,0)))
        return intBbox

    def getBboxPosition(self,bbox:List[int],zoom:Fraction,bboxWOffset=0,bboxHOffset=0,xOffset=0,yOffset=0):
        width=int((bbox[2]-bbox[0])*zoom)+bboxWOffset
        height=int((bbox[3]-bbox[1])*zoom)+bboxHOffset
        top=int(bbox[1]*zoom)+yOffset
        left=int(bbox[0]*zoom)+xOffset
        return width,height,top,left

    def toEnumList(self,num:int)->List[int]:
        binNum=bin(num)
        enumList=[]
        for flag in range(len(binNum)-1,-1,-1):
            if binNum[flag]=='b':
                break
            enumList.append(int(binNum[flag]))
        return enumList

    def deleteUDStr(self,text:str,begnum:int=0):
        m_text=text
        m_begnum=m_text.find('\\ud',begnum)
        if m_begnum>=0:
            m_text=text.replace(text[m_begnum+12:m_begnum+24],"",1)
            return self.deleteUDStr(m_text,m_begnum+12)
        else:
            return str(m_text)

        