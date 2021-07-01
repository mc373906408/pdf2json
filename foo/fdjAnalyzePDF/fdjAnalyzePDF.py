import hashlib
from io import BytesIO
from logging import log
import os

import html
from typing import List
from urllib.parse import urlparse

from redis import Redis
from foo.fdjTools.fdjTools import Tools
from foo.fdjCloud.fdjCloud import Cloud, CloudBucket, CloudUploadType
from foo.fdjPynet.fdjPynet import Pynet
from decimal import Decimal
from fractions import Fraction
import uuid
import fitz
from fitz.fitz import Document, Page, Pixmap, TextPage, sRGB_to_pdf
import pdfplumber
import pdfplumber.pdf as plpdf
import json
import time
import xml.etree.ElementTree as ET
import logging
import copy
from PIL import Image


class AnalyzePDF:
    def __init__(self):
        self.tools = Tools()
        self.cloud = Cloud()
        fitz.Tools().mupdf_display_errors(False)
        self.redis = Redis(host="127.0.0.1", port=6379, db=0)
        self.pptmd5 = 'temp'

    def openPDF(self):
        """打开pdf，并获取页数
        """
        # 打开pdf文件
        self.mu_Document = fitz.Document(self.pdfPath)
        # 拷贝打开一份pdf文件，用于删除图片对象
        self.mu_copyDocument = fitz.Document(self.pdfPath)
        self.pl_Document = pdfplumber.open(self.pdfPath)
        # 重置类变量
        self.imageXrefList = []
        self.imageMap = {}
        # 目前只考虑ppt转的pdf，没有章概念，即第0章，获取pdf页数
        chapterPageCount = Document.chapterPageCount(self.mu_Document, 0)
        # 提前分析pdf，对象保存到字典中
        self.mu_Page = {}
        self.mu_copyPage = {}
        self.pl_Page = {}
        for pno in range(chapterPageCount):
            self.mu_Page[pno] = self.mu_Document.loadPage(pno)
            self.mu_copyPage[pno] = self.mu_copyDocument.loadPage(pno)
            self.pl_Page[pno] = self.pl_Document.pages[pno]
        return chapterPageCount

    def closePDF(self):
        """关闭pdf
        """
        self.mu_Document.close()
        self.mu_copyDocument.close()
        self.pl_Document.close()

    def settingZoom(self, pno):
        """获取缩放比例,ppt 1cm=28.3px,1cm=360000EMU

        PDF Bbox坐标系为左上角0,0
        """
        pl_Page = self.pl_Page[pno]
        # 页面长宽
        self.pageWidth = int(pl_Page.width)
        self.pageHeight = int(pl_Page.height)
        # 计算与H5页面缩放比例，与发给H5页面长宽
        self.zoom = 1
        self.h5Width = 1024
        self.h5Height = 640
        # 图像x,y全局偏移量
        self.h5xOffset = 0
        self.h5yOffset = 0
        # 为了实现坐标精确用分数做zoom
        self.zoom = Fraction(self.h5Width, self.pageWidth)
        if int(self.zoom*self.pageHeight) <= self.h5Height:
            self.h5Height = int(self.zoom*self.pageHeight)
            self.h5yOffset = int((640-self.h5Height)/2)
        else:
            self.zoom = Fraction(self.h5Height, self.pageHeight)
            self.h5Width = int(self.zoom*self.pageWidth)
            self.h5xOffset = int((1024-self.h5Width)/2)

    def getTablesMap(self, pno) -> List:
        """添加表格禁用空间，并识别表格
        """
        self.banBboxs = []
        tableMaps = []
        pl_Page = self.pl_Page[pno]
        # 添加禁用空间，bbox[x0,y0,x1,y2]，pdf坐标系是页面左上角为原点
        # 表格空间
        pl_Tables = plpdf.Page.find_tables(pl_Page)
        pl_TablesText = plpdf.Page.extract_tables(pl_Page)
        for index, table in enumerate(pl_Tables):
            # 表格行列数
            row_count = len(pl_TablesText[index][0])
            column_count = len(pl_TablesText[index])
            # 表格数在4~40之间被认为是表格
            if row_count*column_count<4 or row_count*column_count>40:
                continue
            bbox = []
            for point in table.bbox:
                # 按[x0,y0,x1,y1]分布
                bbox.append(int(round(Decimal(point), 0)))
            # 添加文字、形状禁用识别空间
            self.banBboxs.append(bbox)

            # 表格坐标
            table_width, table_height, table_top, table_left = self.tools.getBboxPosition(
                bbox, self.zoom, 0,0, self.h5xOffset, self.h5yOffset)

            # 判断单元格是否有合并，需要先找出每行每列的坐标
            cell_rowlist = []
            cell_columnlist = []
            for cell in table.cells:
                # 行的y数据
                if cell[1] not in cell_rowlist:
                    cell_rowlist.append(cell[1])
                if cell[3] not in cell_rowlist:
                    cell_rowlist.append(cell[3])
                # 列的x数据
                if cell[0] not in cell_columnlist:
                    cell_columnlist.append(cell[0])
                if cell[2] not in cell_columnlist:
                    cell_columnlist.append(cell[2])
            # 每行、每列坐标
            cell_rowlist.sort()
            cell_columnlist.sort()

            # 给文字赋予坐标
            ctd_text_maps = []
            i = 0
            for row_text_index, row_text in enumerate(pl_TablesText[index]):
                for ctd_text_index, ctd_text in enumerate(row_text):
                    ctd_text_map = {}
                    if ctd_text==None:
                        ctd_text=""
                    ctd_text=ctd_text.replace('\n','<br>')
                    
                    ctd_text_map["id"] = i
                    ctd_text_map["uuid"]=f"tb_{row_text_index}_{ctd_text_index}_{uuid.uuid1().hex}"
                    ctd_text_map["text"] = ctd_text
                    ctd_text_map["bbox"] = [cell_columnlist[ctd_text_index], cell_rowlist[row_text_index],
                                            cell_columnlist[ctd_text_index+1], cell_rowlist[row_text_index+1]]
                    ctd_text_map["height"]=int(cell_rowlist[row_text_index+1]-cell_rowlist[row_text_index])
                    ctd_text_map["width"]=int(cell_columnlist[ctd_text_index+1]-cell_columnlist[ctd_text_index])
                    ctd_text_maps.append(ctd_text_map)
                    i += 1

            # 判断单元格是否有合并关系，放到单元格块中
            ctd_block_list=[]
            for cell in table.cells:
                ctd_list_map={}
                ctd_list_map["ctd_list"]=[]
                for ctd_text_map in ctd_text_maps:
                    if self.tools.isRectangleContainRectangle(cell, ctd_text_map["bbox"]):
                        ctd_list_map["ctd_list"].append(ctd_text_map)
                colspan=1
                rowspan=1
                mergeId=""
                if len(ctd_list_map["ctd_list"])>1:
                    mergeId=ctd_list_map['ctd_list'][0]['uuid']
                    colspan_flag=False
                    for i in range(len(ctd_list_map["ctd_list"])-1):
                        if ctd_list_map["ctd_list"][i+1]["id"]-ctd_list_map["ctd_list"][i]["id"]==1:
                            if colspan_flag==False:
                                colspan+=1
                        else:
                            colspan_flag=True
                            rowspan+=1
                ctd_list_map["colspan"]=colspan
                ctd_list_map["rowspan"]=rowspan
                ctd_list_map["mergeId"]=mergeId
                ctd_block_list.append(ctd_list_map)
            
            # 遍历单元格块
            # 初始化一个一维数组，等所有数据填充完后转换为二维数组
            tableData = [0]*(row_count*column_count)
            for ctd_block in ctd_block_list:
                for ctd in ctd_block["ctd_list"]:
                    ctdMap = {}
                    ctdMap["type"] = "ctd"
                    ctdMap["name"] = "单元格"
                    ctdMap["id"] = ctd["uuid"]
                    ctdMap["width"] = ctd["width"]
                    ctdMap["height"] = ctd["height"]
                    ctdMap["outStyles"] = {}
                    ctdMap["outStyles"]["border"] = "1px solid #ccc"
                    ctdMap["outStyles"]["font-size"] = "20px"
                    ctdMap["outStyles"]["font-family"] = "思源黑体"
                    ctdMap["outStyles"]["color"] = "#333333"
                    ctdMap["outStyles"]["padding-left"] = "10px"
                    ctdMap["outStyles"]["padding-right"] = "10px"
                    ctdMap["outStyles"]["background-color"] = "none"
                    ctdMap["styles"] = {}
                    ctdMap["styles"]["font-size"] = "20px"
                    ctdMap["styles"]["font-family"] = "思源黑体"
                    ctdMap["styles"]["color"] = "#333333"
                    ctdMap["text"] = ctd["text"]
                    ctdMap["html"] = ""
                    ctdMap["check"] = False
                    ctdMap["colspan"]=ctd_block["colspan"]
                    ctdMap["rowspan"]=ctd_block["rowspan"]
                    ctdMap["mergeId"]=ctd_block["mergeId"]

                    ctd_block["colspan"]=ctd_block["rowspan"]=1

                    tableData[ctd["id"]]=ctdMap

            # 一维转二维
            result =[]
            for y in range(column_count):
                for x in range(row_count):
                    if x==0:
                        result.append([])
                    result[y].append(tableData[x+y*row_count])
            tableData=result

            tableMap = {}
            tableMap["name"] = "表格"+str(self.index)
            tableMap["type"] = "ctable"
            tableMap["data"] = {}
            tableMap["data"]["type"] = "ctable"
            tableMap["data"]["name"] = "表格"+str(self.index)
            tableMap["data"]["id"] = uuid.uuid1().hex
            tableMap["data"]["col"] = column_count-1
            tableMap["data"]["row"] = row_count-1
            tableMap["data"]["data"] = tableData
            tableMap["data"]["width"] = table_width
            tableMap["data"]["height"] = table_height
            tableMap["data"]["isTdUpdate"] = False
            tableMap["data"]["styles"] = {}
            tableMap["data"]["styles"]["width"] = "100%"
            tableMap["data"]["styles"]["height"] = "100%"
            tableMap["data"]["styles"]["border-top"] = "1px solid #ccc"
            tableMap["data"]["styles"]["border-left"] = "1px solid #ccc"
            tableMap["data"]["styles"]["border-collapse"] = "collapse"
            tableMap["data"]["styles"]["table-layout"] = "fixed"
            tableMap["data"]["styles"]["font-size"] = "20px"
            tableMap["data"]["styles"]["font-family"] = "思源黑体"
            tableMap["data"]["styles"]["color"] = "#333333"
            tableMap["data"]["styles"]["background-color"] = "transparent"
            tableMap["data"]["styles"]["position"] = "absolute"
            tableMap["data"]["outStyles"] = {}
            tableMap["data"]["outStyles"]["width"] = str(table_width)+"px"
            tableMap["data"]["outStyles"]["height"] = str(table_height)+"px"
            tableMap["data"]["outStyles"]["top"] = str(table_top)+"px"
            tableMap["data"]["outStyles"]["left"] = str(table_left)+"px"
            tableMap["data"]["outStyles"]["position"] = "absolute"
            tableMap["data"]["outStyles"]["min-height"] = str(
                table_height)+"px"
            tableMap["data"]["outStyles"]["background-color"] = "transparent"
            tableMap["data"]["icon"] = "iconlayer_ic_form"
            tableMap["data"]["colData"] = None
            tableMap["active"] = ""
            tableMap["event"] = "none"
            tableMap["aniStyles"] = {}
            tableMap["aniStyles"]["width"] = "100%"
            tableMap["aniStyles"]["height"] = "100%"
            tableMap["aniStyles"]["position"] = "absolute"
            tableMap["aniStyles"]["box-sizing"] = "border-box"
            tableMap["imgUrl"] = ""

            tableMaps.append(tableMap)

        return tableMaps

    def getTextMap(self, pno) -> List:
        """获取pdf文字

        注意1:当文字落在表格空间内(bbox)将被认为表格内文字
        注意2:表格空间内的文字会出现在文字识别中，需要去重，具体是根据bbox位置进行去重，就算文字没有被表格识别，只要bbox有相交

        """
        mu_Page = self.mu_Page[pno]
        # 识别文字
        mu_TextPage = Page.getTextPage(mu_Page)
        mu_Texts = TextPage.extractDICT(mu_TextPage)

        textMaps = []

        for blocksTexts in mu_Texts['blocks']:
            flag = False
            bbox = self.tools.toIntBbox(blocksTexts['bbox'])
            # 抛弃禁用识别区文字
            for banBbox in self.banBboxs:
                flag = self.tools.isRectangleOverlap(banBbox, bbox)
                if flag is True:
                    break
            if flag is True:
                continue

            # 文字块中识别行
            for index, line in enumerate(blocksTexts['lines']):
                vertical = False
                spanText = ""
                richText = False
                spanWidth = -1
                spanHeight = -1
                spanTop = -1
                spanLeft = -1
                textName = ""
                color = "333333"
                textSize = 26
                bboxWOffset=0
                bboxHOffset=0

                superscripted = False  # 上标
                italic = False  # 斜体
                serifed = False  # 衬体
                monospaced = False  # 等距
                bold = False  # 加粗

                # 启用富文本
                if len(line['spans']) > 1:
                    richText = True
                # 取每行中精准的文字、字体、颜色、字体大小
                for span in line['spans']:
                    superscripted = False  # 上标
                    italic = False  # 斜体
                    serifed = False  # 衬体
                    monospaced = False  # 等距
                    bold = False  # 加粗

                    # 颜色十进制转十六进制字符串
                    color_rgb=sRGB_to_pdf(span['color'])
                    rgb=(int(color_rgb[0]*255.0),int(color_rgb[1]*255.0),int(color_rgb[2]*255.0))
                    color='%02x%02x%02x'%rgb
                    # 名字
                    if len(textName) < 10:
                        textName += span['text'][:(10-len(textName))]
                    # 字体大小
                    textSize = int(round(span['size']))
                    lastbboxWOffset=copy.deepcopy(bboxWOffset)
                    lastbboxHOffset=copy.deepcopy(bboxHOffset)
                    # bboxWOffset=textSize*3
                    bboxHOffset=10
                    # 位置
                    width, height, top, left = self.tools.getBboxPosition(
                        span["bbox"], self.zoom, bboxWOffset,bboxHOffset, self.h5xOffset, self.h5yOffset)
                    # 求字形
                    spanFlags = int(span["flags"])
                    if spanFlags != 0:
                        spanFlagsList = self.tools.toEnumList(spanFlags)
                        for index, spanFlag in enumerate(spanFlagsList):
                            if spanFlag == 1:
                                if index == 0:
                                    superscripted = True
                                elif index == 1:
                                    italic = True
                                elif index == 2:
                                    serifed = True
                                elif index == 3:
                                    monospaced = True
                                elif index == 4:
                                    bold = True
                    # 求文字方向
                    if line["dir"][0] == 0.0 and line["dir"][0] > 0:
                        # 竖向
                        vertical = True

                    # 文字原文
                    text = span['text']
                    # 所有文字都填到注释里
                    self.remark += text
                    # 对特殊文字打个补丁，删掉多余的特殊文字
                    # spanText = eval(self.tools.deleteUDStr(repr(spanText)))

                    if richText:
                        # 编辑富文本
                        boldText = ""
                        if bold:
                            boldText = "font-family:思源黑体-bold;"
                        italicText = ""
                        if italic:
                            italicText = "font-style:italic;"
                        superscriptedBegin = ""
                        superscriptedEnd = ""
                        if superscripted:
                            superscriptedBegin = "<sup>"
                            superscriptedEnd = "</sup>"

                        spanText += f'''<span style="color:#{color};{boldText}{italicText}font-size:{textSize}px;">{superscriptedBegin}{text}{superscriptedEnd}</span>'''

                        if spanTop < 0 or spanTop>top:
                            spanTop = top
                        if spanLeft < 0:
                            spanLeft = left
                        if spanWidth < 0:
                            spanWidth = width
                        else:
                            if vertical == False:
                                spanWidth = spanWidth+width-lastbboxWOffset
                            
                        if spanHeight < 0:
                            spanHeight = height
                        else:
                            if vertical:
                                spanHeight = spanHeight+height-lastbboxHOffset
                            elif spanHeight<height:
                                spanHeight=height
                    else:
                        spanTop = top
                        spanLeft = left
                        spanWidth = width
                        spanHeight = height
                        spanText = text

                spanWidth=int(spanWidth*1.25)
                # 备注空行
                self.remark += " "

                # 构造Map
                textMap = {}
                textMap["name"] = textName
                textMap["type"] = "text"
                textMap["data"] = {}
                textMap["data"]["type"] = "text"
                textMap["data"]["name"] = textName
                textMap["data"]["id"] = uuid.uuid1().hex
                textMap["data"]["text"] = spanText
                textMap["data"]["outStyles"] = {}
                textMap["data"]["outStyles"]["width"] = str(spanWidth)+"px"
                textMap["data"]["outStyles"]["height"] = str(
                    spanHeight)+"px"
                textMap["data"]["outStyles"]["top"] = str(spanTop)+"px"
                textMap["data"]["outStyles"]["left"] = str(spanLeft)+"px"
                textMap["data"]["outStyles"]["position"] = "absolute"
                textMap["data"]["outStyles"]["z-index"] = self.index
                textMap["data"]["styles"] = {}
                textMap["data"]["styles"]["width"] = "100%"
                textMap["data"]["styles"]["min-height"] = "100%"
                textMap["data"]["styles"]["height"] = "auto"
                textMap["data"]["styles"]["font-size"] = "%dpx" % (textSize)
                textMap["data"]["styles"]["font-family"] = "思源黑体"
                textMap["data"]["styles"]["color"] = f"#{color}"
                textMap["data"]["styles"]["position"] = "absolute"
                if richText==False:
                    if vertical:
                        textMap["data"]["styles"]["writing-mode"] = "vertical-lr"
                    if italic:
                        textMap["data"]["styles"]["font-style"] = "italic"
                    if bold:
                        textMap["data"]["styles"]["font-family"] = "思源黑体-bold"
                textMap["data"]["icon"] = "iconlayer_ic_text"
                textMap["aniStyles"] = {}
                textMap["aniStyles"]["width"] = "100%"
                textMap["aniStyles"]["height"] = "100%"
                textMap["aniStyles"]["position"] = "absolute"
                textMap["aniStyles"]["box-sizing"] = "border-box"
                textMap["zIndex"] = self.index
                textMap["index"] = self.index

                textMaps.append(textMap)
                self.index += 1

        return textMaps

    def getImageMap(self, pno) -> List:
        """获取pdf图片，上传到oss，以链接做传输

        缺陷1:无法识别svg图片
        缺陷2:无法识别形状
        """
        def recoveImage(xref, smake):
            """为图片恢复透明图层
            """

            # 获取原始图片数据和蒙版数据
            pix1 = fitz.Pixmap(self.mu_Document, xref)
            pix2 = fitz.Pixmap(self.mu_Document, smake)

            try:
                mode="RGB"
                if pix1.alpha>0:
                    mode="RGBA"
                pix=Image.frombytes(mode,(pix1.irect[2],pix1.irect[3]),pix1.samples)
                mask=Image.frombytes("L",(pix2.irect[2],pix2.irect[3]),pix2.samples)
                tpix=Image.new("RGBA",pix.size)
                tpix.paste(pix,None,mask)
                bf=BytesIO()
                tpix.save(bf,"png")
                
                return bf.getvalue()
            except:
                pix = fitz.Pixmap(pix1)
                pix.setAlpha(pix2.samples)
                pix1 = pix2 = None

                if pix.colorspace.n != 4:
                    return Pixmap.getPNGData(pix)
                tpix = fitz.Pixmap(fitz.csRGB, pix)
                return Pixmap.getPNGData(tpix)



        mu_Page = self.mu_Page[pno]

        # 获取pdf图片布局
        mu_ImagePageList = Page.getImageList(mu_Page, full=True)
        # 解析每张图片
        imageMaps = []
        for index, imagePage in enumerate(mu_ImagePageList):
            imageName = "图片"+str(index+2)
            imageXref = imagePage[0]
            imageSmask = imagePage[1]

            try:
                imageBbox = Page.getImageBbox(mu_Page, imagePage)
            except:
                continue

            bbox = self.tools.toIntBbox(imageBbox)
            width, height, top, left = self.tools.getBboxPosition(
                bbox, self.zoom, 0,0, self.h5xOffset, self.h5yOffset)

            objectName = ""
            if imageXref not in self.imageXrefList:
                self.imageXrefList.append(imageXref)
                Document._deleteObject(self.mu_copyDocument, imageXref)
                # 获取图片对象
                pix = {}
                if imageSmask > 0:
                    pix["image"] = recoveImage(imageXref, imageSmask)
                    pix["ext"] = "png"
                else:
                    # 不用恢复图片
                    pix = Document.extractImage(self.mu_Document, imageXref)

                # 记录图片信息值
                self.imageMap[imageXref] = {}
                self.imageMap[imageXref]["md5"] = hashlib.md5(
                    pix["image"]).hexdigest()
                self.imageMap[imageXref]["ext"] = pix["ext"]
                objectName = "Uploads/kj/%s.%s" % (
                    self.imageMap[imageXref]["md5"], self.imageMap[imageXref]["ext"])

                # 上传到云
                self.cloud.upload(CloudBucket.imageEndpoint(), CloudBucket.imageBucket(),
                                  objectName, CloudUploadType.BUFFER, pix["image"])
            else:
                objectName = "Uploads/kj/%s.%s" % (
                    self.imageMap[imageXref]["md5"], self.imageMap[imageXref]["ext"])

            # 构造Map
            imageMap = {}
            imageMap["name"] = imageName
            imageMap["type"] = "image"
            imageMap["data"] = {}
            imageMap["data"]["type"] = "image"
            imageMap["data"]["name"] = imageName
            imageMap["data"]["id"] = uuid.uuid1().hex
            imageMap["data"]["url"] = "https://wb-image.fudaojun.com/%s" % (
                objectName)
            imageMap["data"]["styles"] = {}
            imageMap["data"]["styles"]["width"] = "100%"
            imageMap["data"]["styles"]["height"] = "100%"
            imageMap["data"]["styles"]["position"] = "absolute"
            imageMap["data"]["outStyles"] = {}
            imageMap["data"]["outStyles"]["width"] = str(width)+"px"
            imageMap["data"]["outStyles"]["height"] = str(height)+"px"
            imageMap["data"]["outStyles"]["top"] = str(top)+"px"
            imageMap["data"]["outStyles"]["left"] = str(left)+"px"
            imageMap["data"]["outStyles"]["position"] = "absolute"
            imageMap["data"]["outStyles"]["z-index"] = self.index
            imageMap["data"]["icon"] = "iconlayer_ic_image1"
            imageMap["aniStyles"] = {}
            imageMap["aniStyles"]["width"] = "100%"
            imageMap["aniStyles"]["height"] = "100%"
            imageMap["aniStyles"]["position"] = "absolute"
            imageMap["aniStyles"]["box-sizing"] = "border-box"
            imageMap["zIndex"] = self.index
            imageMap["index"] = self.index
            imageMap["bbox"] = bbox
            imageMap["area"] = width*height

            imageMaps.append(imageMap)
            self.index += 1

        # 空出svg位置
        # self.svgindex = copy.deepcopy(self.index)
        # self.index += 1

        # 调整图片顺序，图片处于重叠关系时，大图片放下面
        # for wwww in range(len(imageMaps)+1):
        #     wrt = False
        #     # 发生交换以后，重新进行双循环
        #     for index, imageA in enumerate(imageMaps):
        #         brt = False
        #         for imageB in imageMaps:
        #             # 跳过自己
        #             if imageA["data"]["id"] == imageB["data"]["id"]:
        #                 continue
        #             # 如果发生重叠
        #             if self.tools.isRectangleOverlap(imageA["bbox"], imageB["bbox"]):
        #                 # 面积比较
        #                 if imageA["area"] > imageB["area"]:
        #                     # 上下位置比较
        #                     if imageA["index"] > imageB["index"]:
        #                         i = copy.deepcopy(imageB["index"])
        #                         j = copy.deepcopy(imageA["index"])
        #                         imageB["index"] = j
        #                         imageB["zIndex"] = j
        #                         imageB["data"]["outStyles"]["z-index"] = j
        #                         imageA["index"] = i
        #                         imageA["zIndex"] = i
        #                         imageA["data"]["outStyles"]["z-index"] = i

        #                         brt = True
        #                         break
        #         if brt:
        #             break
        #         if index == len(imageMaps)-1:
        #             wrt = True
        #     if wrt:
        #         break

        for image in imageMaps:
            image.pop("bbox")
            image.pop("area")

        return imageMaps

    def getShapeMap(self, pno) -> List:
        """获取pdf形状数据

        因为形状数据太多，都转成图片或者由opencv绘制，都会对CPU造成极大负担，于是反其道
        将页面缩放后导出svg，去掉文字、图片、表格区域
        """
        def deleteObject(root: ET.Element):
            """删除文字、表格，无限递归直到遇到错误
            """
            deleteChildList = []
            try:
                for children in root:
                    # 文字
                    if children.tag == "{http://www.w3.org/2000/svg}text":
                        deleteChildList.append(children)
                    if children.tag == "{http://www.w3.org/2000/svg}path":
                        pathMap = children.attrib
                        path_d = []
                        path_transform = []
                        # 找出d定位
                        for path_d_split in pathMap['d'].split():
                            try:
                                path_d.append(float(path_d_split))
                            except:
                                continue
                        path_d = [path_d[i:i+2]
                                  for i in range(0, len(path_d), 2)]
                        # 找出transform矩阵
                        if 'matrix' in pathMap['transform']:
                            for f in pathMap['transform'][7:-1].split(','):
                                try:
                                    path_transform.append(float(f))
                                except:
                                    continue
                        # 根据矩阵变化，计算出点的实际x,y,去掉缩放
                        # 公式  X'=aX+cY+e
                        #       Y'=bX+dY+f
                        path_xy = []
                        a = 1
                        b = path_transform[1]
                        c = path_transform[2]
                        d = -1
                        e = path_transform[4]
                        f = path_transform[5]

                        for path_d_child in path_d:
                            x = path_d_child[0]
                            y = path_d_child[1]
                            # y轴有一个36的偏移值，不知道从何来，总之需要去掉
                            path_xy.append(
                                [int(round(a*x+c*y+e, 0)), int(round(b*x+d*y+f, 0))-36])

                        # 坐标点转bbox，只转换线和矩形
                        bbox = []
                        if len(path_xy) == 2:
                            bbox.append(path_xy[0][0])
                            bbox.append(path_xy[0][1])
                            bbox.append(path_xy[1][0])
                            bbox.append(path_xy[1][1])
                        elif len(path_xy) == 4:
                            bbox.append(path_xy[3][0])
                            bbox.append(path_xy[3][1])
                            bbox.append(path_xy[1][0])
                            bbox.append(path_xy[1][1])

                        for banBbox in self.banBboxs:
                            # 表格矩形向外膨胀5px，增加识别率
                            swell = 5
                            banBbox = [banBbox[0]-swell, banBbox[1] -
                                       swell, banBbox[2]+swell, banBbox[3]+swell]
                            if self.tools.isRectangleContainRectangle(banBbox, bbox):
                                deleteChildList.append(children)

                        # 判断最底层是否有颜色，如果底层有颜色将其图层放置在最底层
                        if bbox[2]-bbox[0] == self.pageWidth and bbox[3]-bbox[1] == self.pageHeight:
                            if pathMap["fill"]=="#ffffff":
                                deleteChildList.append(children)
                            elif pathMap["fill"] is not None:
                                self.svgindex = 0

                    deleteObject(children)
                for deleteChild in deleteChildList:
                    root.remove(deleteChild)
            except:
                return root
            else:
                return root

        mu_copyPage = self.mu_copyPage[pno]
        # 解析为svg，进行后续处理
        m = fitz.Matrix(fitz.Identity)
        m.preScale(self.zoom, self.zoom)
        mu_svg = Page.getSVGimage(mu_copyPage, matrix=m, text_as_path=False)

        # 以XML方法解析
        try:
            root = ET.fromstring(html.unescape(mu_svg))
            root = deleteObject(root)
            xmlData = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        except:
            return []
        else:
            # 上传到云
            objectName = "Uploads/kj/%s.svg" % (
                hashlib.md5(xmlData).hexdigest())
            self.cloud.upload(CloudBucket.imageEndpoint(), CloudBucket.imageBucket(
            ), objectName, CloudUploadType.BUFFER, xmlData)

            self.svgindex=0
            # 构造Map
            imageMap = {}
            imageMap["name"] = "图片1"
            imageMap["type"] = "image"
            imageMap["data"] = {}
            imageMap["data"]["type"] = "image"
            imageMap["data"]["name"] = "图片1"
            imageMap["data"]["id"] = uuid.uuid1().hex
            imageMap["data"]["url"] = "https://wb-image.fudaojun.com/%s" % (
                objectName)
            imageMap["data"]["styles"] = {}
            imageMap["data"]["styles"]["width"] = "100%"
            imageMap["data"]["styles"]["height"] = "100%"
            imageMap["data"]["styles"]["position"] = "absolute"
            imageMap["data"]["outStyles"] = {}
            imageMap["data"]["outStyles"]["width"] = str(self.h5Width)+"px"
            imageMap["data"]["outStyles"]["height"] = str(self.h5Height)+"px"
            imageMap["data"]["outStyles"]["top"] = str(self.h5yOffset)+"px"
            imageMap["data"]["outStyles"]["left"] = str(self.h5xOffset)+"px"
            imageMap["data"]["outStyles"]["position"] = "absolute"
            imageMap["data"]["outStyles"]["z-index"] = self.svgindex
            imageMap["data"]["icon"] = "iconlayer_ic_image1"
            imageMap["aniStyles"] = {}
            imageMap["aniStyles"]["width"] = "100%"
            imageMap["aniStyles"]["height"] = "100%"
            imageMap["aniStyles"]["position"] = "absolute"
            imageMap["aniStyles"]["box-sizing"] = "border-box"
            imageMap["zIndex"] = self.svgindex
            imageMap["index"] = self.svgindex

            return [imageMap]

    def analyzPDF(self, pdfPath,debug=False):
        """分析pdf的包装接口
        """
        self.pdfPath = pdfPath
        self.pdfName = os.path.basename(pdfPath)[:-4]
        chapterPageCount = self.openPDF()
        # 从第0页开始迭代
        pageMaps = []
        for pno in range(chapterPageCount):
            # 大于100页不解析
            if pno > 99:
                break
            # 记录进度
            if debug==False:
                self.redis.set("progress_"+self.pptmd5,int((pno+1)/(chapterPageCount*2)*100)+50)

            # 初始化注释
            self.remark = ""
            # 初始化数组下标
            self.index = 0
            self.settingZoom(pno)

            tableMap = self.getTablesMap(pno)
            imageMap = self.getImageMap(pno)
            textMap = self.getTextMap(pno)
            # svgImageMap = self.getShapeMap(pno)

            id = uuid.uuid1().hex

            # 截取原始图
            mu_Page = self.mu_Page[pno]
            m = fitz.Matrix(self.zoom, self.zoom)
            orgin_img = Page.getPixmap(mu_Page, m)
            # 处理原始图片为 1024 640 即: 8:5
            # 如果图片是 16:9 即: 8:4.5 则上下留白(居中)
            # 如果图片是 4:3 即 8:6 则左右留白(居中)
            # 为了实现坐标精确用分数做zoom
            h5Width, h5Height, h5yOffset, h5xOffset = 1024, 640, 0, 0
            origin_width = orgin_img.width
            origin_height = orgin_img.height
            zoom = Fraction(h5Width, origin_width)
            if int(zoom * origin_height) <= h5Height:
                h5Height = int(zoom * origin_height)
                h5yOffset = int((640 - h5Height) / 2)
            else:
                zoom = Fraction(h5Height, origin_height)
                h5Width = int(zoom * origin_width)
                h5xOffset = int((1024 - h5Width) / 2)

            mode = "RGB"
            if orgin_img.alpha > 0:
                mode = "RGBA"

            pix = Image.frombytes(
                mode, (orgin_img.irect[2], orgin_img.irect[3]), orgin_img.samples
            )
            pix.resize((h5Width, h5Height))
            # 填充空白区域
            box = Image.new(size=(1024, 640), mode=pix.mode, color=(255,255,255,255))
            box.paste(pix, box=(h5xOffset, h5yOffset))
            bf = BytesIO()
            box.save(bf,"png")

            date = time.strftime("%Y%m%d", time.localtime())
            objectName = f"{date}/{self.pdfName}/{self.pdfName}/{id}.jpg"
            self.cloud.upload(
                CloudBucket.imageEndpoint(), CloudBucket.imageBucket(),
                objectName, CloudUploadType.BUFFER, bf.getvalue()
            )
            pix.close()
            box.close()

            # 构造页面map
            pageMap = {}
            pageMap["remark"] = self.remark
            pageMap["styles"] = {}
            pageMap["styles"]["width"] = "1024px"
            pageMap["styles"]["height"] = "640px"
            pageMap["styles"]["position"] = "relative"
            pageMap["styles"]["background-color"] = "#FFFFFF"
            pageMap["styles"]["background-image"] = ""
            pageMap["styles"]["background-size"] = "100% 100%"
            # if self.svgindex == 0:
            #     pageMap["components"] = svgImageMap+imageMap+textMap+tableMap
            # else:
            #     pageMap["components"] = imageMap+svgImageMap+textMap+tableMap
            pageMap["components"] = imageMap+textMap+tableMap
            pageMap["activeIndex"] = str(pno)
            pageMap["imageUrl"] = objectName
            pageMap["imageBase64"] = ""
            pageMap["fileSize"] = 0
            pageMap["isEdit"] = False
            pageMap["isUpload"] = False
            pageMap["isThemes"] = False
            pageMap["isThemeAll"] = True
            pageMap["animations"] = {}
            pageMap["id"] = id

            for component in pageMap["components"]:
                # 给表格定位
                if component["type"] == "ctable":
                    component["data"]["outStyles"]["z-index"] = self.index
                    component["zIndex"] = self.index
                    component["index"] = self.index
                    self.index += 1

                # 如果将svg图放置最底层，其他图片需要上移一层
                # if self.svgindex == 0:
                #     if component["type"] == "image" and component["name"] != "图片1":
                #         component["data"]["outStyles"]["z-index"] += 1
                #         component["zIndex"] += 1
                #         component["index"] += 1

            # 列表排序
            for component in pageMap["components"]:
                component["index"] = self.index-component["index"]-1
            pageMap["components"]=sorted(pageMap["components"],key=lambda x:x['index'])

            pageMaps.append(pageMap)
        jsonData = json.dumps(pageMaps, ensure_ascii=True)

        # 上传到云
        objectName = "courseware/office/%s/%s.json" % (
            (time.strftime('%Y%m%d', time.localtime())),  hashlib.md5(jsonData.encode("utf-8")).hexdigest())
        self.cloud.upload(
            CloudBucket.jsonEndpoint(), CloudBucket.jsonBucket(), objectName,
            CloudUploadType.STRING, jsonData
        )

        self.closePDF()

        if debug==False:
            try:
                os.remove(pdfPath)
            except:
                pass

        res = "https://json.fudaojun.com/"+objectName
        if debug==False:
            self.redis.set(self.pptmd5,res)

        logging.warn(f"任务结束:返回Json：{res}")

        return res

    def pptDownload(self, url, filePath):
        objectName = urlparse(url).path[1:]
        return self.cloud.download(CloudBucket.pptEndpoint(), CloudBucket.pptBucket(), objectName, filePath)

    def ppt2json(self, pptPath):
        m_pynet = Pynet()
        if m_pynet.pptCompatibilityFix(pptPath) == False:
            logging.error("任务结束:pptCompatibilityFix失败")
            self.redis.set("error_"+self.pptmd5, "PPT文件无法解析，请修改后再试")
            try:
                os.remove(pptPath)
            except:
                pass
            return ""
        # 记录进度
        self.redis.set("progress_"+self.pptmd5, 25)

        pdfPath = str(os.path.splitext(pptPath)[0]+".pdf").replace('/', "\\")
        if m_pynet.ppt2pdfCom(pptPath, pdfPath) == False:
            logging.error("任务结束:ppt2pdfCom失败")
            self.redis.set("error_"+self.pptmd5, "PPT文件无法转换PDF，请修改后再试")
            try:
                os.remove(pptPath)
            except:
                pass
            return ""
        # 记录进度
        self.redis.set("progress_"+self.pptmd5, 50)
        try:
            os.remove(pptPath)
        except:
            pass
        try:
            return self.analyzPDF(pdfPath)
        except e:
            print(e)
            logging.error("任务结束:analyzPDF失败")
            self.redis.set("error_"+self.pptmd5, "PDF文件无法解析，请修改后再试")
            return ""

    def run(self, url):
        # 查询是否之前任务已经解析过
        pptName = url.split('/')[-1]
        self.pptmd5 = pptName.split('.')[0]
        if self.redis.exists(self.pptmd5) == 1:
            return str(self.redis.get(self.pptmd5), 'utf-8')

        pptPath = "C:/Users/Administrator/Desktop/ppt/"+pptName
        if self.pptDownload(url, pptPath) == 203:
            logging.error("任务结束:pptDownload失败")
            self.redis.set("error_"+self.pptmd5, "PPT文件下载失败，请稍后再试")
            try:
                os.remove(pptPath)
            except:
                pass
            return "error"

        # 记录进度
        self.redis.set("progress_"+self.pptmd5, 10)

        res = self.ppt2json(pptPath)
        if res == "":
            return "error"
        return res
